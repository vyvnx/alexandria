import math

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


def _vec(x, y, z=0.0):
    """1024-dim unit vector spanned by the first three axes — hand-set cosines."""
    v = [0.0] * 1024
    n = math.sqrt(x * x + y * y + z * z)
    v[0], v[1], v[2] = x / n, y / n, z / n
    return v


# geometry shared by the knn-scorer tests: extracted C sits above merge_threshold
# from dismissed A (cos 0.908) but even closer to interest B (cos 0.978).
_A, _B, _C = _vec(1, 0), _vec(0.8, 0.6), _vec(2.6, 1.2)


def test_interest_rescues_near_dismissed_topic(store):
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    _dismiss(store, "exam scoring", _A)
    nodes = [ExtractedNode("cloud certification design", "concept")]
    kept, _ = drop_dismissed(store, nodes, [_C], _settings(),
                             positives=[("cloud solution design", 2.0, _B)])
    assert [n.name for n in kept] == ["cloud certification design"]


def test_near_dismissed_without_closer_interest_drops(store):
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    _dismiss(store, "exam scoring", _A)
    nodes = [ExtractedNode("exam registration", "concept")]
    # no positives at all -> suppressed
    kept, _ = drop_dismissed(store, nodes, [_C], _settings())
    assert kept == []
    # a positive exists but is farther than the dismissal -> still suppressed
    kept, _ = drop_dismissed(store, nodes, [_C], _settings(),
                             positives=[("Victorian era", 3.0, _vec(0, 1))])
    assert kept == []


def test_exact_name_dismissal_is_never_rescued(store):
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    _dismiss(store, "Patreon", _A)
    # identical vector to a heavy interest, but the user dismissed this exact name
    nodes = [ExtractedNode("Patreon", "concept")]
    kept, _ = drop_dismissed(store, nodes, [_B], _settings(),
                             positives=[("membership economics", 5.0, _B)])
    assert kept == []


def test_novel_topic_passes_with_both_pools_present(store):
    # the guardrail: far from the negative pool -> pass, no matter how far
    # from the positive pool. novelty is never suppressed.
    if not store.vec_available:
        pytest.skip("sqlite-vec required to snapshot embeddings")
    _dismiss(store, "exam scoring", _A)
    nodes = [ExtractedNode("Victorian era", "concept")]
    kept, _ = drop_dismissed(store, nodes, [_vec(0, 0, 1)], _settings(),
                             positives=[("cloud solution design", 2.0, _B)])
    assert [n.name for n in kept] == ["Victorian era"]
