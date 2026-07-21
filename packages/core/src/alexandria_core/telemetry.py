"""LLM cost telemetry (roadmap F1) and the ingest execution ledger.

Provider calls are metered by the thin Metered* proxies; token usage flows
from providers into the active call record via add_usage(), so multi-round
methods (repair retries) accumulate into one row. Executions group calls per
ingest run; the execution table doubles as the persistent job queue (A1).
Writes are best-effort: telemetry must never fail an ingest.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from .logging_config import get_logger
from .providers.base import Extraction, Relation, TopicMatch, Vector

log = get_logger("telemetry")

# $ per 1M tokens for the configured model (gpt-4o-mini); 0 ⇒ cost reported
# as tokens only. Becomes a per-model table when cost-aware routing (F4) lands.
PRICE_IN_PER_MTOK = 0.15
PRICE_OUT_PER_MTOK = 0.60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|succeeded|failed
  stage TEXT NOT NULL DEFAULT 'queued',
  payload TEXT,                            -- ingest request json (the job-queue half)
  result TEXT,
  error TEXT,
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS llm_call (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id INTEGER,                    -- NULL outside an ingest (e.g. /search embeds)
  task TEXT NOT NULL,                      -- summarize|extract|relate|same_topic|embed|describe_image
  model TEXT NOT NULL DEFAULT '',
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_usd REAL,
  duration_ms INTEGER NOT NULL,
  at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ActiveCall:
    task: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    has_usage: bool = False


_current_call: ContextVar[_ActiveCall | None] = ContextVar("alex_llm_call", default=None)
_current_execution: ContextVar[int | None] = ContextVar("alex_execution", default=None)


def add_usage(prompt_tokens: int, completion_tokens: int, model: str = "") -> None:
    """Report one API round-trip's usage. Called by providers; no-op when the
    call isn't metered. Accumulates, so retries within one method sum up."""
    rec = _current_call.get()
    if rec is None:
        return
    rec.prompt_tokens += prompt_tokens or 0
    rec.completion_tokens += completion_tokens or 0
    rec.has_usage = True
    if model:
        rec.model = model


def set_current_execution(execution_id: int | None) -> None:
    """Attribute subsequent metered calls (in this thread/task) to an execution."""
    _current_execution.set(execution_id)


class TelemetryStore:
    """SQLite ledger of executions and per-call telemetry. Embedded, no daemon;
    shared across the request threads and the ingest worker (lock-serialized)."""

    def __init__(self, db_path: str, *, price_in_per_mtok: float = PRICE_IN_PER_MTOK,
                 price_out_per_mtok: float = PRICE_OUT_PER_MTOK):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        # ponytail: two flat prices for the one configured model; becomes a
        # per-model table when cost-aware routing (F4) lands
        self.price_in = price_in_per_mtok
        self.price_out = price_out_per_mtok
        with self._lock, self.conn:
            self.conn.executescript(_SCHEMA)

    # ── executions ──────────────────────────────────────────────────────────
    def finish_execution(self, execution_id: int, status: str, *,
                         result: dict | None = None, error: str | None = None) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE execution SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                (status, json.dumps(result) if result is not None else None,
                 error, _now(), execution_id))

    def set_stage(self, execution_id: int, stage: str) -> None:
        with self._lock, self.conn:
            self.conn.execute("UPDATE execution SET stage=? WHERE id=?",
                              (stage, execution_id))

    def get_execution(self, execution_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM execution WHERE id=?",
                                    (execution_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("payload", "result"):
            d[key] = json.loads(d[key]) if d[key] else None
        return d

    def list_executions(self, limit: int = 50) -> list[dict]:
        """Newest-first executions with token/cost totals and a per-task rollup."""
        with self._lock:
            execs = self.conn.execute(
                "SELECT id, source, status, stage, queued_at, started_at, finished_at"
                " FROM execution ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            ids = [r["id"] for r in execs]
            marks = ",".join("?" * len(ids))
            calls = self.conn.execute(
                f"SELECT execution_id, task, COUNT(*) AS calls,"
                f" SUM(prompt_tokens) AS prompt_tokens,"
                f" SUM(completion_tokens) AS completion_tokens,"
                f" SUM(cost_usd) AS cost_usd"
                f" FROM llm_call WHERE execution_id IN ({marks})"
                f" GROUP BY execution_id, task", ids).fetchall() if ids else []

        tasks: dict[int, dict] = {i: {} for i in ids}
        for c in calls:
            tasks[c["execution_id"]][c["task"]] = {
                "calls": c["calls"], "prompt_tokens": c["prompt_tokens"],
                "completion_tokens": c["completion_tokens"], "cost_usd": c["cost_usd"]}

        out = []
        for r in execs:
            per_task = tasks[r["id"]].values()
            costs = [t["cost_usd"] for t in per_task if t["cost_usd"] is not None]
            out.append({
                **{k: r[k] for k in ("id", "source", "status", "stage",
                                     "queued_at", "started_at", "finished_at")},
                "duration_ms": _elapsed_ms(r["started_at"], r["finished_at"]),
                "prompt_tokens": sum(t["prompt_tokens"] or 0 for t in per_task),
                "completion_tokens": sum(t["completion_tokens"] or 0 for t in per_task),
                "cost_usd": sum(costs) if costs else None,
                "tasks": tasks[r["id"]],
            })
        return out

    # ── rollups (roadmap F2/F3) ──────────────────────────────────────────────
    def spend_since(self, iso: str) -> float:
        """Total $ spent on llm calls at/after `iso` (unpriced calls count 0)."""
        with self._lock:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_call WHERE at >= ?",
                (iso,)).fetchone()
        return row["c"]

    def usage(self, days: int = 30) -> dict:
        """Where the money goes: totals + per-day/per-task/per-source rollups."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            total = self.conn.execute(
                "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost,"
                " COALESCE(SUM(prompt_tokens), 0) AS pt,"
                " COALESCE(SUM(completion_tokens), 0) AS ct"
                " FROM llm_call WHERE at >= ?", (since,)).fetchone()
            per_day = self.conn.execute(
                "SELECT substr(at, 1, 10) AS day, COUNT(*) AS calls,"
                " COALESCE(SUM(cost_usd), 0) AS cost FROM llm_call"
                " WHERE at >= ? GROUP BY day ORDER BY day", (since,)).fetchall()
            per_task = self.conn.execute(
                "SELECT task, COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost,"
                " COALESCE(SUM(prompt_tokens), 0) AS pt,"
                " COALESCE(SUM(completion_tokens), 0) AS ct"
                " FROM llm_call WHERE at >= ? GROUP BY task", (since,)).fetchall()
            per_source = self.conn.execute(
                "SELECT e.source AS source, COUNT(*) AS calls,"
                " COALESCE(SUM(c.cost_usd), 0) AS cost"
                " FROM llm_call c JOIN execution e ON c.execution_id = e.id"
                " WHERE c.at >= ? GROUP BY e.source ORDER BY cost DESC LIMIT 20",
                (since,)).fetchall()
        return {
            "days": days,
            "total_calls": total["calls"],
            "total_cost_usd": total["cost"],
            "prompt_tokens": total["pt"],
            "completion_tokens": total["ct"],
            "per_day": [{"day": r["day"], "calls": r["calls"], "cost_usd": r["cost"]}
                        for r in per_day],
            "per_task": {r["task"]: {"calls": r["calls"], "cost_usd": r["cost"],
                                     "prompt_tokens": r["pt"], "completion_tokens": r["ct"]}
                         for r in per_task},
            "per_source": [{"source": r["source"], "calls": r["calls"],
                            "cost_usd": r["cost"]} for r in per_source],
        }

    # ── job queue (roadmap A1): an execution row doubles as the ingest job ──
    def enqueue(self, source: str, payload: dict) -> int:
        """Queue an ingest job; the row starts as status=queued/stage=queued."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO execution (source, payload, queued_at) VALUES (?, ?, ?)",
                (source, json.dumps(payload), _now()))
        return cur.lastrowid

    def claim_next(self) -> dict | None:
        """Flip the oldest queued job to running and return it (None if idle)."""
        with self._lock, self.conn:
            row = self.conn.execute(
                "SELECT id FROM execution WHERE status='queued'"
                " ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return None
            self.conn.execute(
                "UPDATE execution SET status='running', started_at=? WHERE id=?",
                (_now(), row["id"]))
        return self.get_execution(row["id"])

    def recover(self) -> int:
        """Startup recovery: jobs interrupted mid-run are failed (a re-run could
        double-charge llm calls); queued jobs survive untouched and just run."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE execution SET status='failed',"
                " error='interrupted by restart', finished_at=?"
                " WHERE status='running'", (_now(),))
        return cur.rowcount

    # ── per-call recording (used by the Metered* proxies) ───────────────────
    def _record_call(self, rec: _ActiveCall, duration_ms: int) -> None:
        cost = None
        if rec.has_usage and (self.price_in or self.price_out):
            cost = (rec.prompt_tokens / 1e6 * self.price_in
                    + rec.completion_tokens / 1e6 * self.price_out)
        try:
            with self._lock, self.conn:
                self.conn.execute(
                    "INSERT INTO llm_call (execution_id, task, model, prompt_tokens,"
                    " completion_tokens, cost_usd, duration_ms, at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (_current_execution.get(), rec.task, rec.model,
                     rec.prompt_tokens if rec.has_usage else None,
                     rec.completion_tokens if rec.has_usage else None,
                     cost, duration_ms, _now()))
        except sqlite3.Error:
            log.warning("telemetry write failed for task=%s — call not recorded", rec.task)


def _elapsed_ms(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return int(delta.total_seconds() * 1000)


def _metered(store: TelemetryStore, inner, task: str, fn):
    rec = _ActiveCall(task=task, model=getattr(inner, "model", "") or "")
    token = _current_call.set(rec)
    t0 = time.perf_counter()
    try:
        return fn()
    finally:
        _current_call.reset(token)
        store._record_call(rec, int((time.perf_counter() - t0) * 1000))


class MeteredLLM:
    """LLMProvider proxy: one llm_call row per method call."""

    def __init__(self, inner, store: TelemetryStore):
        self.inner, self._store = inner, store

    def summarize(self, text: str) -> str:
        return _metered(self._store, self.inner, "summarize",
                        lambda: self.inner.summarize(text))

    def extract(self, text: str, **kw) -> Extraction:
        return _metered(self._store, self.inner, "extract",
                        lambda: self.inner.extract(text, **kw))

    def relate(self, names: list[str], text: str) -> list[Relation]:
        return _metered(self._store, self.inner, "relate",
                        lambda: self.inner.relate(names, text))

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        return _metered(self._store, self.inner, "same_topic",
                        lambda: self.inner.same_topic(label_a, label_b))

    def answer(self, question: str, context: str) -> str:
        return _metered(self._store, self.inner, "answer",
                        lambda: self.inner.answer(question, context))


class MeteredEmbedder:
    """EmbeddingProvider proxy — local model, so duration only (no usage)."""

    def __init__(self, inner, store: TelemetryStore):
        self.inner, self._store = inner, store

    def embed(self, texts: list[str], *, kind: Literal["query", "document"]) -> list[Vector]:
        return _metered(self._store, self.inner, "embed",
                        lambda: self.inner.embed(texts, kind=kind))


class MeteredVision:
    """VisionProvider proxy."""

    def __init__(self, inner, store: TelemetryStore):
        self.inner, self._store = inner, store

    def describe_image(self, images: list[bytes], prompt: str) -> str:
        return _metered(self._store, self.inner, "describe_image",
                        lambda: self.inner.describe_image(images, prompt))
