"""Intake (roadmap A3): the curated source registry and its topics.

Not a crawler — a list of feeds you trust, each polled on its own cadence by
the ingest worker, every discovered item gated by topic relevance before it
costs a single llm token. Tables live in the graph db file (they are the
user's domain data), on a separate lock-serialized connection.
"""
from __future__ import annotations

import math
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


def topic_names(registry: IntakeRegistry, store, settings) -> list[str]:
    """The gate's vocabulary (decision fork #2, both ways): explicit curated
    topics first, then the graph's own confirmed interests, deduped."""
    explicit = [t["name"] for t in registry.list_topics()]
    learned = [name for name, _, _ in store.interest_pool(
        half_life_days=settings.interest_half_life_days,
        min_weight=settings.interest_min_weight)][:settings.learned_topics_top_n]
    return list(dict.fromkeys(explicit + learned))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _parse_feed_links(xml_text: str) -> list[str]:
    """Item links from an RSS (`item/link` text) or Atom (`entry/link[@href]`,
    alternate rel only) document, deduped in feed order. No host filtering —
    the user curated this feed, so its links are trusted (unlike trafilatura's
    courlan validation, which drops local/IP hosts)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    links: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "item":
            for child in node:
                if child.tag.rsplit("}", 1)[-1] == "link" and child.text:
                    links.append(child.text.strip())
        elif tag == "entry":
            for child in node:
                if (child.tag.rsplit("}", 1)[-1] == "link"
                        and child.get("rel", "alternate") == "alternate"
                        and child.get("href")):
                    links.append(child.get("href").strip())
    return list(dict.fromkeys(links))


def discover_items(feed_url: str) -> list[str]:
    """Article links for a feed url. The network seam — monkeypatched in tests.
    Feed documents are parsed directly; anything else (e.g. a homepage) falls
    back to trafilatura's feed discovery."""
    from trafilatura import fetch_url, feeds
    raw = fetch_url(feed_url)
    links = _parse_feed_links(raw) if raw else []
    return links or feeds.find_feed_urls(feed_url)


def poll_feeds(registry: IntakeRegistry, store, embedder, telemetry, settings, *,
               now: str | None = None, discover=None, load=None) -> int:
    """One poll pass over the due feeds: discover items, drop what's seen or
    already ingested, and enqueue the rest through the A1 job queue. Returns
    how many items were enqueued. A broken feed logs and waits its cadence —
    it never kills the pass."""
    from .ingest.loaders import load_url
    discover = discover or discover_items
    load = load or load_url

    due = registry.due_feeds(now)
    if not due:  # the worker calls this on every idle tick — stay cheap
        return 0

    # relevance gate (A3b): embed the topic vocabulary once per pass; items
    # scoring under the threshold never cost an llm token. no topics ⇒ the
    # curation itself is the filter, admit everything.
    names = topic_names(registry, store, settings)
    topic_vecs = embedder.embed(names, kind="query") if names else []

    enqueued = 0
    for feed in due:
        try:
            links = discover(feed["url"])
        except Exception:
            log.warning("feed discovery failed for %s — retrying next cadence",
                        feed["url"])
            registry.mark_polled(feed["id"], now=now)
            continue
        fresh = [u for u in links
                 if not registry.item_seen(feed["id"], u)
                 and store.find_source_by_url(u) is None]
        # ponytail: cap per poll pass = backpressure; a burst waits for the
        # next cadence instead of flooding the queue
        fresh = fresh[:settings.feed_batch_max]
        if fresh:
            log.info("feed %s: %d new item(s)", feed["url"], len(fresh))
        for link in fresh:
            try:
                doc = load(link)
            except Exception:
                doc = None
            if doc is None or not doc.text:
                registry.record_item(feed["id"], link, "error")
                continue
            score = None
            if topic_vecs:
                (vec,) = embedder.embed([doc.text[:2000]], kind="document")
                score = max(_cosine(vec, tv) for tv in topic_vecs)
                if score < settings.relevance_threshold:
                    log.info("filtered %s (score %.2f < %.2f)",
                             link, score, settings.relevance_threshold)
                    registry.record_item(feed["id"], link, "filtered", score)
                    continue
            telemetry.enqueue(link, {"url": link})
            registry.record_item(feed["id"], link, "enqueued", score)
            enqueued += 1
        registry.mark_polled(feed["id"], now=now)
    return enqueued
