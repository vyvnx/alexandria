from datetime import datetime, timedelta, timezone

import pytest

from alexandria_core.config import Settings
from alexandria_core.digest import build_digest, render_digest
from alexandria_core.graph.models import KIND_CONCEPT, KIND_SOURCE
from alexandria_core.graph.store import GraphStore


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm="fake")


def _old():
    return (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()


def _backdate(store, *, node_ids=(), all_edges=False):
    for nid in node_ids:
        store.conn.execute("UPDATE nodes SET created_at=? WHERE id=?", (_old(), nid))
    if all_edges:
        store.conn.execute("UPDATE edges SET created_at=?", (_old(),))
    store.conn.commit()


def test_digest_counts_only_the_window(settings):
    store = GraphStore(":memory:")
    store.init_schema()
    fresh = store.add_node(KIND_CONCEPT, "fresh idea")
    stale = store.add_node(KIND_CONCEPT, "old idea")
    sid = store.add_node(KIND_SOURCE, "src")
    store.add_source(sid, url=None, author=None, published_at=None,
                     raw_text="", my_note=None, summary="")
    store.add_edge(sid, fresh, "about", from_source_id=sid)
    _backdate(store, node_ids=[stale])

    d = build_digest(store, settings, days=7)
    assert d["days"] == 7
    assert d["new_sources"] == 1
    assert d["new_nodes"] == 2  # fresh concept + the source; stale excluded
    assert [n["name"] for n in d["top_new"]] == ["fresh idea"]
    store.close()


def test_resurface_finds_untouched_high_value_nodes(settings):
    store = GraphStore(":memory:")
    store.init_schema()
    hub = store.add_node(KIND_CONCEPT, "forgotten hub")
    spokes = [store.add_node(KIND_CONCEPT, f"spoke {i}") for i in range(4)]
    for s in spokes:
        store.add_edge(hub, s, "uses")
    _backdate(store, node_ids=[hub, *spokes], all_edges=True)

    d = build_digest(store, settings, days=7)
    assert "forgotten hub" in [n["name"] for n in d["resurface"]]

    # touching the hub this week removes it from the resurface list
    recent = store.add_node(KIND_CONCEPT, "recent")
    store.add_edge(hub, recent, "uses")
    d2 = build_digest(store, settings, days=7)
    assert "forgotten hub" not in [n["name"] for n in d2["resurface"]]
    store.close()


def test_digest_empty_store_and_rendering(settings):
    store = GraphStore(":memory:")
    store.init_schema()
    d = build_digest(store, settings)
    assert d["new_sources"] == 0 and d["new_nodes"] == 0
    assert d["top_new"] == [] and d["resurface"] == [] and d["trending"] == []
    assert d["contradictions"] == 0
    text = render_digest(d)
    assert "0" in text  # renders without crashing on the empty shape
    store.close()
