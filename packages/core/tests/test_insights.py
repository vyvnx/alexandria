import pytest

from alexandria_core.config import Settings
from alexandria_core.graph.models import KIND_CONCEPT, KIND_ENTITY, KIND_SOURCE
from alexandria_core.graph.store import GraphStore
from alexandria_core.insights import compute_insights


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm="fake")


def _seed(store):
    """two topic clusters bridged by one concept, plus a contradicts edge"""
    def concept(name):
        return store.add_node(KIND_CONCEPT, name)

    def source_about(nodes):
        sid = store.add_node(KIND_SOURCE, "src")
        store.add_source(sid, url=None, author=None, published_at=None,
                         raw_text="", my_note=None, summary="")
        for n in nodes:
            store.add_edge(sid, n, "about", from_source_id=sid)
        return sid

    # cluster 1: graphs / embeddings / vectors, densely tied
    graphs, embeddings, vectors = concept("graphs"), concept("embeddings"), concept("vectors")
    store.add_edge(graphs, embeddings, "uses")
    store.add_edge(embeddings, vectors, "uses")
    store.add_edge(graphs, vectors, "uses")
    # cluster 2: history / victorian / empire
    history, victorian, empire = concept("history"), concept("victorian"), concept("empire")
    store.add_edge(history, victorian, "extends")
    store.add_edge(victorian, empire, "extends")
    store.add_edge(history, empire, "extends")
    # the bridge between both worlds
    bridge = concept("knowledge organization")
    store.add_edge(graphs, bridge, "uses")
    store.add_edge(bridge, history, "uses")
    # sources touch both clusters (drives interest weights)
    source_about([graphs, embeddings])
    source_about([graphs, vectors])
    source_about([history, victorian])
    # a documented disagreement
    a, b = concept("flat earth"), concept("round earth")
    store.add_edge(a, b, "contradicts", evidence="the horizon curves")
    return {"bridge": bridge, "graphs": graphs}


def test_insights_shape_and_content(settings):
    store = GraphStore(":memory:")
    store.init_schema()
    ids = _seed(store)
    ins = compute_insights(store, settings)

    assert ins["stats"]["nodes"] == store_len(store) and ins["stats"]["edges"] > 0
    names = [i["name"] for i in ins["strongest_interests"]]
    assert names and "src" not in names  # sources never rank as interests
    assert all(i["score"] > 0 for i in ins["strongest_interests"])

    assert len(ins["communities"]) >= 2
    assert all(c["size"] >= 1 and c["label"] for c in ins["communities"])

    bridge_names = [b["name"] for b in ins["bridges"]]
    assert "knowledge organization" in bridge_names

    assert ins["contradictions"] == [{
        "a": "flat earth", "b": "round earth", "evidence": "the horizon curves"}]

    for pair in ins["suggested_connections"]:
        assert pair["a"]["name"] != pair["b"]["name"]
        assert pair["common"] >= 2
    store.close()


def store_len(store):
    return len(store.all_nodes())


def test_insights_on_empty_store(settings):
    store = GraphStore(":memory:")
    store.init_schema()
    ins = compute_insights(store, settings)
    assert ins["stats"] == {"nodes": 0, "edges": 0}
    assert ins["strongest_interests"] == []
    assert ins["communities"] == []
    assert ins["bridges"] == []
    assert ins["suggested_connections"] == []
    assert ins["trending"] == []
    assert ins["contradictions"] == []
    store.close()
