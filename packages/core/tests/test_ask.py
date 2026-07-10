import pytest

from alexandria_core.ask import ask, retrieve
from alexandria_core.config import Settings
from alexandria_core.graph.models import KIND_CONCEPT, KIND_SOURCE
from alexandria_core.graph.store import GraphStore
from alexandria_core.providers.fake import FakeEmbedder, FakeLLM


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm="fake")


@pytest.fixture
def seeded():
    store = GraphStore(":memory:")
    store.init_schema()
    if not store.vec_available:
        pytest.skip("sqlite-vec required for graphrag retrieval")
    emb = FakeEmbedder(dim=1024)
    concept = store.add_node(KIND_CONCEPT, "attention",
                             {"description": "weighting mechanism in transformers"})
    store.add_embedding(concept, emb.embed(["attention"], kind="document")[0])
    sid = store.add_node(KIND_SOURCE, "Attention is all you need")
    store.add_source(sid, url="https://arxiv.org/1706.03762", author=None,
                     published_at=None, raw_text="the transformer relies on attention",
                     my_note=None, summary="introduces the transformer architecture")
    store.add_embedding(sid, emb.embed(["transformer paper"], kind="document")[0])
    store.add_edge(sid, concept, "about", evidence="core topic", from_source_id=sid)
    yield store, emb, concept, sid
    store.close()


def test_retrieve_returns_numbered_passages_with_neighbors(seeded):
    store, emb, concept, sid = seeded
    passages = retrieve(store, emb, "what is attention?")
    assert [p["n"] for p in passages] == list(range(1, len(passages) + 1))
    ids = {p["node_id"] for p in passages}
    assert concept in ids and sid in ids  # seed plus its neighbor
    by_id = {p["node_id"]: p for p in passages}
    assert "transformer architecture" in by_id[sid]["text"]  # summary quoted
    assert "weighting mechanism" in by_id[concept]["text"]


def test_ask_cites_the_passages(seeded, settings):
    store, emb, _, _ = seeded
    res = ask(store, emb, FakeLLM(), settings, "what is attention?")
    assert res["answer"]
    assert res["passages"] >= 2
    ns = {c["n"] for c in res["citations"]}
    assert ns == set(range(1, res["passages"] + 1))
    assert all(c["name"] for c in res["citations"])


def test_ask_empty_graph_never_calls_the_llm(settings):
    store = GraphStore(":memory:")
    store.init_schema()

    class _Boom:
        def answer(self, q, ctx):
            raise AssertionError("llm must not be called on an empty graph")

    res = ask(store, FakeEmbedder(dim=1024), _Boom(), settings, "anything?")
    assert res["passages"] == 0 and res["citations"] == []
    assert "nothing" in res["answer"].lower()
    store.close()
