"""Intake (roadmap A3): the curated source registry and its topics.

Not a crawler — a list of feeds you trust, each polled on its own cadence by
the ingest worker, every discovered item gated by topic relevance before it
costs a single llm token. Tables live in the graph db file (they are the
user's domain data), on a separate lock-serialized connection.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .logging_config import get_logger

log = get_logger("intake")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feed (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  url             TEXT NOT NULL UNIQUE,
  cadence_minutes INTEGER NOT NULL DEFAULT 60,
  active          INTEGER NOT NULL DEFAULT 1,
  last_polled_at  TEXT,
  created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topic (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  weight     REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feed_item (
  feed_id INTEGER NOT NULL REFERENCES feed(id),
  url     TEXT NOT NULL,
  status  TEXT NOT NULL,             -- enqueued|filtered|error
  score   REAL,
  seen_at TEXT NOT NULL,
  PRIMARY KEY (feed_id, url)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntakeRegistry:
    def __init__(self, db_path: str):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self.conn:
            self.conn.executescript(_SCHEMA)

    # ── feeds ────────────────────────────────────────────────────────────────
    def add_feed(self, url: str, cadence_minutes: int = 60) -> int:
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO feed (url, cadence_minutes, created_at) VALUES (?, ?, ?)",
                (url, cadence_minutes, _now()))
        return cur.lastrowid

    def list_feeds(self) -> list[dict]:
        with self._lock:
            feeds = [dict(r) for r in self.conn.execute(
                "SELECT * FROM feed ORDER BY id").fetchall()]
            counts = self.conn.execute(
                "SELECT feed_id, status, COUNT(*) AS n FROM feed_item"
                " GROUP BY feed_id, status").fetchall()
        by_feed: dict[int, dict] = {}
        for c in counts:
            by_feed.setdefault(c["feed_id"], {})[c["status"]] = c["n"]
        for f in feeds:
            got = by_feed.get(f["id"], {})
            f["items"] = {s: got.get(s, 0) for s in ("enqueued", "filtered", "error")}
        return feeds

    def remove_feed(self, feed_id: int) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM feed_item WHERE feed_id=?", (feed_id,))
            self.conn.execute("DELETE FROM feed WHERE id=?", (feed_id,))

    def due_feeds(self, now: str | None = None) -> list[dict]:
        """Active feeds never polled, or whose cadence has elapsed."""
        now_dt = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        with self._lock:
            feeds = self.conn.execute(
                "SELECT * FROM feed WHERE active=1 ORDER BY id").fetchall()
        due = []
        for f in feeds:
            last = f["last_polled_at"]
            if last is None or now_dt >= (datetime.fromisoformat(last)
                                          + timedelta(minutes=f["cadence_minutes"])):
                due.append(dict(f))
        return due

    def mark_polled(self, feed_id: int, now: str | None = None) -> None:
        with self._lock, self.conn:
            self.conn.execute("UPDATE feed SET last_polled_at=? WHERE id=?",
                              (now or _now(), feed_id))

    def poll_now(self, feed_id: int) -> None:
        """Clear the poll timestamp so the worker treats the feed as due."""
        with self._lock, self.conn:
            self.conn.execute("UPDATE feed SET last_polled_at=NULL WHERE id=?", (feed_id,))

    def feed_exists(self, feed_id: int) -> bool:
        with self._lock:
            return self.conn.execute("SELECT 1 FROM feed WHERE id=?",
                                     (feed_id,)).fetchone() is not None

    # ── items ────────────────────────────────────────────────────────────────
    def item_seen(self, feed_id: int, url: str) -> bool:
        with self._lock:
            return self.conn.execute(
                "SELECT 1 FROM feed_item WHERE feed_id=? AND url=?",
                (feed_id, url)).fetchone() is not None

    def record_item(self, feed_id: int, url: str, status: str,
                    score: float | None = None) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO feed_item (feed_id, url, status, score, seen_at)"
                " VALUES (?, ?, ?, ?, ?)", (feed_id, url, status, score, _now()))

    # ── topics ───────────────────────────────────────────────────────────────
    def add_topic(self, name: str, weight: float = 1.0) -> int:
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO topic (name, weight, created_at) VALUES (?, ?, ?)",
                (name, weight, _now()))
        return cur.lastrowid

    def list_topics(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM topic ORDER BY id").fetchall()]

    def remove_topic(self, topic_id: int) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM topic WHERE id=?", (topic_id,))

    def topic_exists(self, topic_id: int) -> bool:
        with self._lock:
            return self.conn.execute("SELECT 1 FROM topic WHERE id=?",
                                     (topic_id,)).fetchone() is not None

    def close(self) -> None:
        self.conn.close()
