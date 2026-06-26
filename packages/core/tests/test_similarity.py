import pytest

from alexandria_core.graph.store import GraphStore
from alexandria_core.graph.models import KIND_CONCEPT
from alexandria_core.graph import similarity

EMBED_DIM = 1024


def _vec(seed: float):
    v = [0.0] * EMBED_DIM
    v[0] = seed
    v[1] = 1.0 - abs(seed)
    return v


@pytest.fixture
def store():
    s = GraphStore(":memory:")
    s.init_schema()
    if not s.vec_available:
        pytest.skip("sqlite-vec extension not loadable in this Python build")
    yield s
    s.close()


def test_knn_orders_by_similarity(store):
    a = store.add_node(KIND_CONCEPT, "A"); store.add_embedding(a, _vec(1.0))
    b = store.add_node(KIND_CONCEPT, "B"); store.add_embedding(b, _vec(0.9))
    c = store.add_node(KIND_CONCEPT, "C"); store.add_embedding(c, _vec(-1.0))
    hits = store.knn(_vec(1.0), k=3)
    ids = [nid for nid, _ in hits]
    assert ids[0] == a and ids[1] == b      # nearest first
    assert ids[-1] == c                       # opposite vector last
    assert all(-1.001 <= score <= 1.001 for _, score in hits)


def test_top_k_similar_excludes_self_and_threshold(store):
    a = store.add_node(KIND_CONCEPT, "A"); va = _vec(1.0); store.add_embedding(a, va)
    b = store.add_node(KIND_CONCEPT, "B"); store.add_embedding(b, _vec(0.95))
    c = store.add_node(KIND_CONCEPT, "C"); store.add_embedding(c, _vec(-1.0))
    out = similarity.top_k_similar(store, a, va, k=5, threshold=0.5)
    ids = [nid for nid, _ in out]
    assert a not in ids          # self excluded
    assert b in ids              # similar, above threshold
    assert c not in ids          # below threshold
