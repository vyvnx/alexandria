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
