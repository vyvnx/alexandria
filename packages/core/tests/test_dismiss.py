import pytest

from alexandria_core.config import Settings
from alexandria_core.graph.models import KIND_CONCEPT
from alexandria_core.graph.store import GraphStore
from alexandria_core.ingest.resolve import drop_dismissed
from alexandria_core.providers.base import ExtractedNode
from alexandria_core.providers.fake import FakeEmbedder


@pytest.fixture
def store():
    s = GraphStore(":memory:")
    s.init_schema()
    yield s
    s.close()


def _settings():
    return Settings(_env_file=None, llm="fake")


def _dismiss(store, name, vec=None):
    """Create a concept node (optionally with an embedding) and dismiss it."""
    nid = store.add_node(KIND_CONCEPT, name)
    if vec is not None:
        store.add_embedding(nid, vec)
    store.dismiss_node(nid)


def test_empty_dismissed_table_passes_everything_through(store):
    nodes = [ExtractedNode("anything", "concept")]
    vecs = [[0.0] * 8]
    kept, kept_vecs = drop_dismissed(store, nodes, vecs, _settings())
    assert kept == nodes
    assert kept_vecs == vecs


def test_exact_name_match_is_suppressed(store):
    _dismiss(store, "Patreon")
    emb = FakeEmbedder()
    nodes = [ExtractedNode("Patreon", "concept"),
             ExtractedNode("cloud solution design", "concept")]
    vecs = emb.embed([n.name for n in nodes], kind="document")
    kept, kept_vecs = drop_dismissed(store, nodes, vecs, _settings())
    assert [n.name for n in kept] == ["cloud solution design"]
    assert len(kept_vecs) == 1


def test_canonical_variant_is_suppressed(store):
    # possessive + case variants collapse to the same canonical key
    _dismiss(store, "Exam Scoring")
    nodes = [ExtractedNode("exam scoring's", "concept")]
    vecs = FakeEmbedder().embed(["exam scoring's"], kind="document")
    kept, _ = drop_dismissed(store, nodes, vecs, _settings())
    assert kept == []


def test_embedding_match_above_merge_threshold_is_suppressed(store):
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    vec = FakeEmbedder().embed(["membership platform"], kind="document")[0]
    _dismiss(store, "Patreon", vec)
    # different name (no canonical match) but an identical vector -> cosine 1.0
    nodes = [ExtractedNode("Patreon membership", "concept")]
    kept, _ = drop_dismissed(store, nodes, [vec], _settings())
    assert kept == []


def test_dissimilar_topic_survives(store):
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    emb = FakeEmbedder()
    _dismiss(store, "Patreon", emb.embed(["membership platform"], kind="document")[0])
    nodes = [ExtractedNode("Victorian era", "concept")]
    vecs = emb.embed(["Victorian era"], kind="document")
    kept, _ = drop_dismissed(store, nodes, vecs, _settings())
    assert [n.name for n in kept] == ["Victorian era"]
