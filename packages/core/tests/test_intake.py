import sqlite3

import pytest

from alexandria_core.intake import IntakeRegistry


@pytest.fixture
def reg():
    r = IntakeRegistry(":memory:")
    yield r
    r.close()


def test_add_list_remove_feed(reg):
    fid = reg.add_feed("https://blog.example/rss", cadence_minutes=30)
    (feed,) = reg.list_feeds()
    assert feed["id"] == fid
    assert feed["url"] == "https://blog.example/rss"
    assert feed["cadence_minutes"] == 30
    assert feed["last_polled_at"] is None
    assert feed["items"] == {"enqueued": 0, "filtered": 0, "error": 0}
    reg.remove_feed(fid)
    assert reg.list_feeds() == []


def test_duplicate_feed_url_raises(reg):
    reg.add_feed("https://a/rss")
    with pytest.raises(sqlite3.IntegrityError):
        reg.add_feed("https://a/rss")


def test_due_feeds(reg):
    fid = reg.add_feed("https://a/rss", cadence_minutes=60)
    # never polled -> due
    assert [f["id"] for f in reg.due_feeds("2026-07-10T12:00:00+00:00")] == [fid]
    reg.mark_polled(fid, now="2026-07-10T12:00:00+00:00")
    # just polled -> not due
    assert reg.due_feeds("2026-07-10T12:30:00+00:00") == []
    # past its cadence -> due again
    assert [f["id"] for f in reg.due_feeds("2026-07-10T13:00:01+00:00")] == [fid]


def test_poll_now_makes_feed_due(reg):
    fid = reg.add_feed("https://a/rss")
    reg.mark_polled(fid, now="2026-07-10T12:00:00+00:00")
    reg.poll_now(fid)
    assert [f["id"] for f in reg.due_feeds("2026-07-10T12:00:01+00:00")] == [fid]


def test_items_seen_and_counted(reg):
    fid = reg.add_feed("https://a/rss")
    assert reg.item_seen(fid, "https://a/post-1") is False
    reg.record_item(fid, "https://a/post-1", "enqueued", score=0.8)
    reg.record_item(fid, "https://a/post-2", "filtered", score=0.1)
    reg.record_item(fid, "https://a/post-3", "error")
    assert reg.item_seen(fid, "https://a/post-1") is True
    (feed,) = reg.list_feeds()
    assert feed["items"] == {"enqueued": 1, "filtered": 1, "error": 1}


def test_topics_crud(reg):
    tid = reg.add_topic("cloud architecture", weight=2.0)
    reg.add_topic("victorian era")
    names = {t["name"]: t for t in reg.list_topics()}
    assert names["cloud architecture"]["weight"] == 2.0
    assert names["victorian era"]["weight"] == 1.0
    with pytest.raises(sqlite3.IntegrityError):
        reg.add_topic("cloud architecture")
    reg.remove_topic(tid)
    assert [t["name"] for t in reg.list_topics()] == ["victorian era"]


# ── poller ────────────────────────────────────────────────────────────────────

from alexandria_core.config import Settings
from alexandria_core.graph.store import GraphStore
from alexandria_core.graph.models import KIND_SOURCE
from alexandria_core.ingest.loaders import LoadedDoc
from alexandria_core.intake import poll_feeds
from alexandria_core.providers.fake import FakeEmbedder
from alexandria_core.telemetry import TelemetryStore


def _doc(url, text="Attention mechanisms power transformers."):
    return LoadedDoc(url=url, title="t", author=None, published_at=None, text=text)


@pytest.fixture
def world(reg):
    store = GraphStore(":memory:")
    store.init_schema()
    yield {
        "reg": reg, "store": store, "embedder": FakeEmbedder(dim=32),
        "telemetry": TelemetryStore(":memory:"),
        "settings": Settings(_env_file=None, llm="fake"),
    }
    store.close()


def _queued_urls(telemetry):
    rows = telemetry.conn.execute(
        "SELECT source FROM execution WHERE status='queued' ORDER BY id").fetchall()
    return [r["source"] for r in rows]


def test_poll_enqueues_new_items_and_marks_polled(world):
    w = world
    fid = w["reg"].add_feed("https://a/rss")
    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=lambda u: ["https://a/p1", "https://a/p2"], load=_doc)
    assert n == 2
    assert _queued_urls(w["telemetry"]) == ["https://a/p1", "https://a/p2"]
    (feed,) = w["reg"].list_feeds()
    assert feed["last_polled_at"] is not None
    assert feed["items"]["enqueued"] == 2
    job = w["telemetry"].claim_next()
    assert job["payload"] == {"url": "https://a/p1"}


def test_poll_skips_seen_and_already_ingested(world):
    w = world
    fid = w["reg"].add_feed("https://a/rss")
    w["reg"].record_item(fid, "https://a/seen", "enqueued")
    sid = w["store"].add_node(KIND_SOURCE, "old")
    w["store"].add_source(sid, url="https://a/ingested", author=None, published_at=None,
                          raw_text="", my_note=None, summary="")
    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=lambda u: ["https://a/seen", "https://a/ingested", "https://a/new"],
                   load=_doc)
    assert n == 1
    assert _queued_urls(w["telemetry"]) == ["https://a/new"]


def test_poll_respects_batch_cap(world):
    w = world
    w["settings"] = Settings(_env_file=None, llm="fake", feed_batch_max=2)
    w["reg"].add_feed("https://a/rss")
    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=lambda u: [f"https://a/p{i}" for i in range(5)], load=_doc)
    assert n == 2


def test_poll_records_error_for_empty_documents(world):
    w = world
    fid = w["reg"].add_feed("https://a/rss")
    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=lambda u: ["https://a/broken"],
                   load=lambda u: _doc(u, text=""))
    assert n == 0
    (feed,) = w["reg"].list_feeds()
    assert feed["items"]["error"] == 1
    assert _queued_urls(w["telemetry"]) == []


def test_poll_survives_discover_failure(world):
    w = world
    w["reg"].add_feed("https://bad/rss")

    def boom(u):
        raise RuntimeError("feed down")

    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=boom, load=_doc)
    assert n == 0
    (feed,) = w["reg"].list_feeds()
    assert feed["last_polled_at"] is not None  # broken feed waits a full cadence


def test_poll_ignores_feeds_not_due(world):
    w = world
    fid = w["reg"].add_feed("https://a/rss", cadence_minutes=60)
    w["reg"].mark_polled(fid)
    n = poll_feeds(w["reg"], w["store"], w["embedder"], w["telemetry"], w["settings"],
                   discover=lambda u: ["https://a/p1"], load=_doc)
    assert n == 0


# ── relevance gate ────────────────────────────────────────────────────────────

from alexandria_core.graph.models import KIND_CONCEPT
from alexandria_core.intake import topic_names


class _KindlessEmbedder(FakeEmbedder):
    """identical text ⇒ identical vector regardless of query/document kind,
    so gate tests can steer cosine scores with exact strings"""

    def embed(self, texts, *, kind):
        return super().embed(texts, kind="document")


def _gate_settings(threshold=0.99):
    # threshold ≈ 1 ⇒ only text identical to a topic is admitted
    return Settings(_env_file=None, llm="fake", relevance_threshold=threshold)


def test_on_topic_item_is_enqueued_with_score(world):
    w = world
    fid = w["reg"].add_feed("https://a/rss")
    w["reg"].add_topic("spaced repetition")
    n = poll_feeds(w["reg"], w["store"], _KindlessEmbedder(dim=64), w["telemetry"],
                   _gate_settings(),
                   discover=lambda u: ["https://a/on"],
                   load=lambda u: _doc(u, text="spaced repetition"))
    assert n == 1
    row = w["reg"].conn.execute("SELECT status, score FROM feed_item").fetchone()
    assert row["status"] == "enqueued"
    assert row["score"] == pytest.approx(1.0, abs=1e-6)


def test_off_topic_item_is_filtered_before_any_llm_cost(world):
    w = world
    w["reg"].add_feed("https://a/rss")
    w["reg"].add_topic("spaced repetition")
    n = poll_feeds(w["reg"], w["store"], _KindlessEmbedder(dim=64), w["telemetry"],
                   _gate_settings(),
                   discover=lambda u: ["https://a/off"],
                   load=lambda u: _doc(u, text="celebrity gossip roundup"))
    assert n == 0
    assert _queued_urls(w["telemetry"]) == []
    row = w["reg"].conn.execute("SELECT status, score FROM feed_item").fetchone()
    assert row["status"] == "filtered"
    assert row["score"] is not None and row["score"] < 0.99


def test_no_topics_admits_everything(world):
    w = world
    w["reg"].add_feed("https://a/rss")
    n = poll_feeds(w["reg"], w["store"], _KindlessEmbedder(dim=64), w["telemetry"],
                   _gate_settings(),
                   discover=lambda u: ["https://a/any"],
                   load=lambda u: _doc(u, text="anything at all"))
    assert n == 1


def test_learned_topics_come_from_the_interest_pool(world):
    w = world
    # a concept recurring across two sources is a confirmed interest
    concept = w["store"].add_node(KIND_CONCEPT, "spaced repetition")
    for _ in range(2):
        sid = w["store"].add_node("source", "s")
        w["store"].add_source(sid, url=None, author=None, published_at=None,
                              raw_text="", my_note=None, summary="")
        w["store"].add_edge(sid, concept, "about", from_source_id=sid)
    names = topic_names(w["reg"], w["store"], _gate_settings())
    assert "spaced repetition" in names
    # and the learned topic gates intake exactly like an explicit one
    w["reg"].add_feed("https://a/rss")
    n = poll_feeds(w["reg"], w["store"], _KindlessEmbedder(dim=64), w["telemetry"],
                   _gate_settings(),
                   discover=lambda u: ["https://a/on"],
                   load=lambda u: _doc(u, text="spaced repetition"))
    assert n == 1


def test_explicit_topics_come_first_and_dedupe(world):
    w = world
    w["reg"].add_topic("aws")
    concept = w["store"].add_node(KIND_CONCEPT, "aws")
    for _ in range(2):
        sid = w["store"].add_node("source", "s")
        w["store"].add_source(sid, url=None, author=None, published_at=None,
                              raw_text="", my_note=None, summary="")
        w["store"].add_edge(sid, concept, "about", from_source_id=sid)
    assert topic_names(w["reg"], w["store"], _gate_settings()) == ["aws"]
