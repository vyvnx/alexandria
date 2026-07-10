import pytest

from alexandria_core.algo import (
    betweenness,
    build_adjacency,
    louvain,
    pagerank,
    suggest_links,
)
from alexandria_core.graph.store import GraphStore
from alexandria_core.graph.models import KIND_CONCEPT, KIND_SOURCE


def _adj(edges):
    """undirected weighted adjacency from (a, b) or (a, b, w) tuples"""
    adj = {}
    for e in edges:
        a, b, w = e if len(e) == 3 else (*e, 1.0)
        adj.setdefault(a, {})[b] = w
        adj.setdefault(b, {})[a] = w
    return adj


def test_pagerank_star_center_dominates():
    adj = _adj([(0, i) for i in range(1, 6)])
    pr = pagerank(adj)
    assert sum(pr.values()) == pytest.approx(1.0, abs=1e-6)
    assert pr[0] == max(pr.values())
    leaves = [pr[i] for i in range(1, 6)]
    assert max(leaves) - min(leaves) < 1e-9  # symmetric leaves rank equally


def test_pagerank_empty_and_singleton():
    assert pagerank({}) == {}
    assert pagerank({7: {}}) == {7: pytest.approx(1.0)}


def test_louvain_finds_two_triangles():
    # two triangles joined by a single bridge edge
    adj = _adj([(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5), (2, 3)])
    comm = louvain(adj)
    assert comm[0] == comm[1] == comm[2]
    assert comm[3] == comm[4] == comm[5]
    assert comm[0] != comm[3]


def test_louvain_empty():
    assert louvain({}) == {}


def test_betweenness_bridge_node_is_highest():
    # barbell: triangle - 6 - triangle; node 6 carries all cross traffic
    adj = _adj([(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5), (2, 6), (6, 3)])
    bt = betweenness(adj)
    assert bt[6] == max(bt.values())
    assert bt[6] > bt[0]


def test_suggest_links_proposes_the_missing_diagonal():
    # square 0-1-2-3 plus diagonal 0-2; the pair (1, 3) shares 2 neighbors
    adj = _adj([(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])
    top = suggest_links(adj, top=3, min_common=2)
    assert (1, 3, 2) in top


def test_suggest_links_skips_already_linked_pairs():
    adj = _adj([(0, 1), (1, 2), (0, 2)])  # triangle: every pair linked
    assert suggest_links(adj, min_common=1) == []


def test_build_adjacency_from_store_weights_and_kind_filter():
    store = GraphStore(":memory:")
    store.init_schema()
    s = store.add_node(KIND_SOURCE, "src")
    a = store.add_node(KIND_CONCEPT, "a")
    b = store.add_node(KIND_CONCEPT, "b")
    store.add_edge(s, a, "about")
    store.add_edge(a, b, "similar-to", weight=0.7)
    adj = build_adjacency(store)
    assert adj[s][a] == 1.0          # typed edge defaults to weight 1
    assert adj[a][b] == 0.7          # similar-to keeps its cosine weight
    concepts_only = build_adjacency(store, include_kinds={KIND_CONCEPT})
    assert s not in concepts_only and concepts_only[a] == {b: 0.7}
    store.close()
