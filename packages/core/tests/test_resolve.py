import math

import pytest

from alexandria_core.config import Settings
from alexandria_core.graph.store import GraphStore
from alexandria_core.graph.models import KIND_CONCEPT, KIND_ENTITY
from alexandria_core.providers.base import ExtractedNode, TopicMatch
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder
from alexandria_core.ingest.resolve import resolve, canonical_name

# default knobs: merge 0.86, ambiguous 0.72, fuzzy_ratio 90
S = Settings(_env_file=None, llm="fake")


@pytest.fixture
def store():
    s = GraphStore(":memory:")
    s.init_schema()
    yield s
    s.close()


def e0():
    """Query unit vector e0 = [1, 0, 0, ...]."""
    v = [0.0] * 1024
    v[0] = 1.0
    return v


def vec(cosine: float):
    """A stored unit vector whose cosine with e0() is exactly `cosine`."""
    v = [0.0] * 1024
    v[0] = cosine
    v[1] = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    return v


# ---- canonical_name (Stage 1 key) -------------------------------------------

def test_canonical_name_possessive():
    assert canonical_name("Dijkstra's Algorithm") == canonical_name("Dijkstra Algorithm")


def test_canonical_name_plural():
    assert canonical_name("Transformers") == canonical_name("Transformer")


def test_canonical_name_word_order():
    assert canonical_name("Dijkstra Algorithm") == canonical_name("Algorithm Dijkstra")


def test_canonical_name_article():
    assert canonical_name("The Transformer") == canonical_name("Transformer")


def test_canonical_name_punctuation_is_stable():
    assert canonical_name("Shortest-Path (Dijkstra)") == "dijkstra path shortest"


def test_canonical_name_short_tokens_not_folded():
    # tokens <= 3 chars keep their trailing 's' (don't fold "RAG"/"rag" oddly)
    assert canonical_name("RAG") == "rag"


# ---- Stage 1: deterministic canonical merge ---------------------------------

def test_possessive_merges_to_existing(store):
    eid = store.add_node(KIND_CONCEPT, "Dijkstra Algorithm", {"description": "x"})
    ex = [ExtractedNode("Dijkstra's Algorithm", "concept", "dup")]
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id == eid


def test_cross_kind_merge_via_stage1(store):
    # stored as entity, re-extracted as concept — Stage 1 is kind-agnostic
    eid = store.add_node(KIND_ENTITY, "Dijkstra Algorithm", {"description": "x"})
    ex = [ExtractedNode("dijkstra algorithm", "concept", "dup")]
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id == eid


def test_within_batch_dedup(store):
    ex = [ExtractedNode("RAG", "concept", "a"), ExtractedNode("rag", "concept", "b")]
    res = resolve(store, ex, [e0(), e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id is None and res[0].batch_canonical is None
    assert res[1].batch_canonical == 0


def test_new_node_when_no_match(store):
    ex = [ExtractedNode("Brand New Thing", "concept", "c")]
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id is None and res[0].batch_canonical is None


# ---- Stage 3: two decoupled thresholds --------------------------------------

def test_embedding_merge_above_threshold(store):
    eid = store.add_node(KIND_CONCEPT, "Gradient Descent", {"description": "x"})
    store.add_embedding(eid, vec(0.9))                       # cosine 0.9 >= merge 0.86
    ex = [ExtractedNode("SGD Optimizer", "concept", "y")]    # unrelated name; embedding decides
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id == eid


def test_no_merge_below_ambiguous(store):
    eid = store.add_node(KIND_CONCEPT, "Gradient Descent", {"description": "x"})
    store.add_embedding(eid, vec(0.6))                       # cosine 0.6 < ambiguous 0.72
    ex = [ExtractedNode("Backpropagation", "concept", "y")]
    # LLM would say yes if consulted — proves the LLM is NOT consulted below the band
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM(default_same_topic=True))
    assert res[0].existing_id is None and res[0].batch_canonical is None


# ---- Stage 3: gray-zone LLM adjudication ------------------------------------

def test_gray_zone_llm_yes_merges(store):
    eid = store.add_node(KIND_CONCEPT, "Neural Net", {"description": "x"})
    store.add_embedding(eid, vec(0.8))                       # gray band [0.72, 0.86)
    ex = [ExtractedNode("Deep Network", "concept", "y")]
    llm = FakeLLM(topic_decisions={("Deep Network", "Neural Net"): True})
    res = resolve(store, ex, [e0()], settings=S, llm=llm)
    assert res[0].existing_id == eid


def test_gray_zone_llm_no_stays_new(store):
    eid = store.add_node(KIND_CONCEPT, "Neural Net", {"description": "x"})
    store.add_embedding(eid, vec(0.8))
    ex = [ExtractedNode("Deep Network", "concept", "y")]
    llm = FakeLLM(topic_decisions={("Deep Network", "Neural Net"): False})
    res = resolve(store, ex, [e0()], settings=S, llm=llm)
    assert res[0].existing_id is None and res[0].batch_canonical is None


def test_no_false_merge_java_javascript(store):
    # high surface similarity, gray-band embedding, but the LLM knows they differ
    eid = store.add_node(KIND_CONCEPT, "JavaScript", {"description": "x"})
    store.add_embedding(eid, vec(0.8))
    ex = [ExtractedNode("Java", "concept", "y")]
    llm = FakeLLM(topic_decisions={("Java", "JavaScript"): False})
    res = resolve(store, ex, [e0()], settings=S, llm=llm)
    assert res[0].existing_id is None


# ---- robustness -------------------------------------------------------------

def test_degraded_mode_stage1_still_merges(store, monkeypatch):
    eid = store.add_node(KIND_CONCEPT, "Transformer", {"description": "x"})
    monkeypatch.setattr(store, "knn", lambda *a, **k: [])    # sqlite-vec unavailable
    ex = [ExtractedNode("transformers", "concept", "dup")]   # canonical-equal after plural fold
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id == eid


def test_fuzzy_proposes_candidate_when_knn_misses(store, monkeypatch):
    # name twin not surfaced by embedding search; fuzzy proposes it, embedding then confirms
    eid = store.add_node(KIND_CONCEPT, "Dijkstra Algorithm", {"description": "x"})
    store.add_embedding(eid, vec(0.9))
    monkeypatch.setattr(store, "knn", lambda *a, **k: [])
    ex = [ExtractedNode("Dijkstra Algorthm", "concept", "typo")]  # one-letter typo, canonical differs
    res = resolve(store, ex, [e0()], settings=S, llm=FakeLLM())
    assert res[0].existing_id == eid


# ---- FakeLLM contract -------------------------------------------------------

def test_fake_llm_same_topic_returns_topicmatch():
    llm = FakeLLM(topic_decisions={("A", "B"): True})
    m = llm.same_topic("A", "B")
    assert isinstance(m, TopicMatch) and m.same_topic is True
    assert llm.same_topic("A", "C").same_topic is False  # default
