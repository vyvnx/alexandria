from datetime import datetime, timedelta, timezone

import pytest

from alexandria_core.graph.store import GraphStore
from alexandria_core.graph.models import KIND_SOURCE, KIND_CONCEPT


@pytest.fixture
def store():
    s = GraphStore(":memory:")
    s.init_schema()
    yield s
    s.close()


def test_add_and_get_node(store):
    nid = store.add_node(KIND_CONCEPT, "Transformers", {"description": "attention model"})
    n = store.get_node(nid)
    assert n.name == "Transformers"
    assert n.kind == KIND_CONCEPT
    assert n.data["description"] == "attention model"
    assert n.created_at is not None


def test_find_by_name(store):
    store.add_node(KIND_CONCEPT, "RAG")
    assert store.find_node_by_name("RAG", KIND_CONCEPT).name == "RAG"
    assert store.find_node_by_name("RAG", KIND_SOURCE) is None


def test_source_side_table(store):
    nid = store.add_node(KIND_SOURCE, "An Article")
    store.add_source(nid, url="http://x", author="A", published_at=None,
                     raw_text="body", my_note="my take", summary="sum")
    src = store.get_source(nid)
    assert src["url"] == "http://x" and src["my_note"] == "my take"


def test_symmetric_edge_canonicalized(store):
    a = store.add_node(KIND_CONCEPT, "A")
    b = store.add_node(KIND_CONCEPT, "B")
    store.add_edge(b, a, "similar-to", weight=0.9)
    edges = store.all_edges()
    assert len(edges) == 1
    assert edges[0].src_id == min(a, b) and edges[0].dst_id == max(a, b)
    # duplicate (reversed) is ignored
    store.add_edge(a, b, "similar-to", weight=0.8)
    assert len(store.all_edges()) == 1


def test_typed_edge_direction_preserved(store):
    a = store.add_node(KIND_CONCEPT, "A")
    b = store.add_node(KIND_CONCEPT, "B")
    store.add_edge(a, b, "uses", evidence="A uses B")
    e = store.all_edges()[0]
    assert (e.src_id, e.dst_id, e.type) == (a, b, "uses")


def test_reach_k_hops(store):
    a = store.add_node(KIND_CONCEPT, "A")
    b = store.add_node(KIND_CONCEPT, "B")
    c = store.add_node(KIND_CONCEPT, "C")
    d = store.add_node(KIND_CONCEPT, "D")
    store.add_edge(a, b, "uses")
    store.add_edge(b, c, "uses")
    store.add_edge(c, d, "uses")
    assert set(store.reach(a, 0)) == {a}
    assert set(store.reach(a, 1)) == {a, b}
    assert set(store.reach(a, 2)) == {a, b, c}


def test_log(store):
    store.log("ingest", "added 3 nodes")
    rows = store.conn.execute("SELECT op, detail FROM log").fetchall()
    assert rows[0][0] == "ingest"


def test_dismiss_node_removes_and_records(store):
    src = store.add_node(KIND_SOURCE, "An Article")
    nid = store.add_node(KIND_CONCEPT, "Patreon", {"description": "membership platform"})
    store.add_embedding(nid, [0.1] * 1024)
    store.add_edge(src, nid, "about")

    name = store.dismiss_node(nid)

    assert name == "Patreon"
    assert store.get_node(nid) is None
    assert store.edges_for(nid) == []
    assert store.get_embedding(nid) is None
    dismissed = store.all_dismissed()
    assert len(dismissed) == 1
    dname, dvec = dismissed[0]
    assert dname == "Patreon"
    if store.vec_available:
        assert dvec is not None and len(dvec) == 1024
        assert abs(dvec[0] - 0.1) < 1e-6
    else:
        assert dvec is None


def test_dismiss_source_node_rejected(store):
    sid = store.add_node(KIND_SOURCE, "An Article")
    with pytest.raises(ValueError):
        store.dismiss_node(sid)
    assert store.get_node(sid) is not None


def test_dismiss_unknown_node_rejected(store):
    with pytest.raises(ValueError):
        store.dismiss_node(999)


def test_all_dismissed_empty_by_default(store):
    assert store.all_dismissed() == []


def _source_about(store, node_ids, ingested_at=None):
    """Add a source node with an about edge to each given node; optionally backdate it."""
    sid = store.add_node(KIND_SOURCE, "src")
    store.add_source(sid, url=None, author=None, published_at=None,
                     raw_text="", my_note=None, summary="")
    for nid in node_ids:
        store.add_edge(sid, nid, "about", from_source_id=sid)
    if ingested_at is not None:
        store.conn.execute("UPDATE sources SET ingested_at=? WHERE node_id=?",
                           (ingested_at, sid))
    return sid


def test_interest_pool_requires_recurrence(store):
    a = store.add_node(KIND_CONCEPT, "cloud design")
    b = store.add_node(KIND_CONCEPT, "one-off")
    _source_about(store, [a, b])
    _source_about(store, [a])
    pool = store.interest_pool(half_life_days=90, min_weight=1.5)
    # only the concept seen across two sources qualifies, weight ~= 2 fresh votes
    assert [name for name, _, _ in pool] == ["cloud design"]
    assert pool[0][1] == pytest.approx(2.0, abs=0.01)


def test_interest_pool_decays_old_sources(store):
    a = store.add_node(KIND_CONCEPT, "aws")
    old = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    _source_about(store, [a], ingested_at=old)
    _source_about(store, [a], ingested_at=old)
    # two sources, but both two half-lives stale -> weight ~= 0.5, interest has drifted away
    assert store.interest_pool(half_life_days=90, min_weight=1.5) == []


def test_source_content_hash_and_finders(store):
    sid = store.add_node(KIND_SOURCE, "s")
    store.add_source(sid, url="https://a.com/x", author=None, published_at=None,
                     raw_text="t", my_note=None, summary="", content_hash="abc123")
    assert store.find_source_by_url("https://a.com/x") == sid
    assert store.find_source_by_hash("abc123") == sid
    assert store.find_source_by_url("https://other") is None
    assert store.find_source_by_hash("nope") is None


def test_init_schema_migrates_pre_hash_sources_table():
    s = GraphStore(":memory:")
    # simulate a db created before the dedup column existed
    s.conn.execute(
        "CREATE TABLE sources (node_id INTEGER PRIMARY KEY, url TEXT, author TEXT,"
        " published_at TEXT, raw_text TEXT, my_note TEXT, summary TEXT, ingested_at TEXT)")
    s.init_schema()
    cols = [r[1] for r in s.conn.execute("PRAGMA table_info(sources)")]
    assert "content_hash" in cols
    s.close()


def test_set_positions_roundtrip_rounded(store):
    a = store.add_node(KIND_CONCEPT, "a")
    b = store.add_node(KIND_CONCEPT, "b")
    assert store.get_node(a).x is None  # unplaced until a layout settles
    saved = store.set_positions({a: (1.23456, -7.891), b: (0.0, 2.5)})
    assert saved == 2
    n = store.get_node(a)
    assert (n.x, n.y) == (1.23, -7.89)


def test_set_positions_ignores_unknown_ids(store):
    a = store.add_node(KIND_CONCEPT, "a")
    saved = store.set_positions({a: (1.0, 1.0), 9999: (2.0, 2.0)})
    assert saved == 1
    assert store.get_node(a).x == 1.0


def test_init_schema_migrates_pre_position_nodes_table():
    s = GraphStore(":memory:")
    # simulate a db created before the position columns existed
    s.conn.execute(
        "CREATE TABLE nodes (id INTEGER PRIMARY KEY, kind TEXT NOT NULL,"
        " name TEXT NOT NULL, data TEXT, created_at TEXT NOT NULL)")
    s.init_schema()
    cols = [r[1] for r in s.conn.execute("PRAGMA table_info(nodes)")]
    assert "x" in cols and "y" in cols
    s.close()
