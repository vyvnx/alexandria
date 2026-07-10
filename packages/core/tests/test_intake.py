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
