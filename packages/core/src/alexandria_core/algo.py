"""Hand-rolled graph algorithms (roadmap D1) — the algo core.

Implemented from the papers, not imported (learning-first, non-goal §7):

- PageRank (Brin & Page 1998): stationary distribution of a random surfer who
  follows edges with probability `damping` and teleports anywhere otherwise.
  Here weighted + undirected: a neighbor's pull is proportional to edge weight.
- Louvain (Blondel et al. 2008): greedy modularity maximization — each node
  moves to the neighboring community with the best modularity gain, then
  communities collapse into super-nodes and the process repeats.
- Betweenness (Brandes 2001): for every source, one BFS forward pass counts
  shortest paths, one backward pass accumulates each node's share of them.
- Link prediction: common-neighbor count over non-adjacent pairs — the
  simplest classical heuristic ("friends of friends").

Everything is deterministic (sorted iteration, no randomness) so results are
reproducible and tests can assert exact structure. Pure Python over an
adjacency dict — a future Rust→WASM core replaces this behind the same
signatures; callers never know.
"""
from __future__ import annotations

from collections import deque

Adjacency = dict[int, dict[int, float]]


def build_adjacency(store, *, include_kinds: set[str] | None = None) -> Adjacency:
    """Undirected weighted adjacency from the live store. Typed edges weigh
    1.0; `similar-to` keeps its cosine weight. Isolated nodes are included
    (pagerank needs the full node set for its distribution)."""
    nodes = store.all_nodes()
    keep = {n.id for n in nodes if include_kinds is None or n.kind in include_kinds}
    adj: Adjacency = {v: {} for v in keep}
    for e in store.all_edges():
        if e.src_id not in keep or e.dst_id not in keep:
            continue
        w = e.weight if e.weight is not None else 1.0
        adj[e.src_id][e.dst_id] = w
        adj[e.dst_id][e.src_id] = w
    return adj


def pagerank(adj: Adjacency, *, damping: float = 0.85, iterations: int = 50,
             ) -> dict[int, float]:
    n = len(adj)
    if n == 0:
        return {}
    rank = dict.fromkeys(adj, 1.0 / n)
    strength = {v: sum(nbrs.values()) for v, nbrs in adj.items()}
    for _ in range(iterations):
        # nodes with no edges have nowhere to send rank — it teleports evenly
        dangling = sum(rank[v] for v in adj if not adj[v])
        base = (1.0 - damping) / n + damping * dangling / n
        nxt = dict.fromkeys(adj, base)
        for v, nbrs in adj.items():
            if not nbrs:
                continue
            share = damping * rank[v] / strength[v]
            for u, w in nbrs.items():
                nxt[u] += share * w
        rank = nxt
    return rank


def louvain(adj: Adjacency, *, resolution: float = 1.0) -> dict[int, int]:
    """node -> community id (0-based, ordered by each community's smallest
    original member, so labels are stable across runs)."""
    if not adj:
        return {}
    node_to_current = {v: v for v in adj}  # original node -> current-level node
    graph = {v: dict(nbrs) for v, nbrs in adj.items()}
    while True:
        comm, improved = _local_move(graph, resolution)
        node_to_current = {orig: comm[cur] for orig, cur in node_to_current.items()}
        if not improved:
            break
        graph = _aggregate(graph, comm)
    # stable relabel: community holding the smallest original node gets id 0
    members: dict[int, list[int]] = {}
    for orig, c in node_to_current.items():
        members.setdefault(c, []).append(orig)
    order = sorted(members, key=lambda c: min(members[c]))
    label = {c: i for i, c in enumerate(order)}
    return {orig: label[c] for orig, c in node_to_current.items()}


def _local_move(graph: Adjacency, resolution: float) -> tuple[dict[int, int], bool]:
    """One louvain phase: sweep nodes (sorted, for determinism), moving each to
    the neighboring community with the best modularity gain, until stable."""
    m2 = sum(sum(nbrs.values()) for nbrs in graph.values())  # = 2m
    comm = {v: v for v in graph}
    if m2 == 0:
        return comm, False
    strength = {v: sum(nbrs.values()) for v, nbrs in graph.items()}
    tot = dict(strength)  # per-community total strength (communities start singleton)
    improved = False
    moved = True
    while moved:
        moved = False
        for v in sorted(graph):
            cv = comm[v]
            links: dict[int, float] = {}  # weight from v into each neighbor community
            for u, w in graph[v].items():
                if u != v:
                    links[comm[u]] = links.get(comm[u], 0.0) + w
            tot[cv] -= strength[v]  # evaluate moves with v taken out
            # comparative modularity gain: k_i_in(c) - γ·Σtot(c)·k_i / 2m
            best_c = cv
            best_gain = links.get(cv, 0.0) - resolution * tot[cv] * strength[v] / m2
            for c in sorted(links):
                gain = links[c] - resolution * tot.get(c, 0.0) * strength[v] / m2
                if gain > best_gain + 1e-12:
                    best_c, best_gain = c, gain
            tot[best_c] = tot.get(best_c, 0.0) + strength[v]
            if best_c != cv:
                comm[v] = best_c
                moved = improved = True
    return comm, improved


def _aggregate(graph: Adjacency, comm: dict[int, int]) -> Adjacency:
    """Collapse communities into super-nodes; internal edges become self-loops."""
    agg: Adjacency = {}
    for v, nbrs in graph.items():
        cv = comm[v]
        agg.setdefault(cv, {})
        for u, w in nbrs.items():
            cu = comm[u]
            agg[cv][cu] = agg[cv].get(cu, 0.0) + w
    return agg


def betweenness(adj: Adjacency, *, pivots: int = 200) -> dict[int, float]:
    """Brandes betweenness (unweighted shortest paths). Exact up to `pivots`
    nodes; above that, sampled from the highest-degree pivots and rescaled.
    # ponytail: sampling bounds the O(V·E) cost; exact pass only on small graphs
    """
    nodes = sorted(adj)
    bt = dict.fromkeys(nodes, 0.0)
    if len(nodes) <= pivots:
        sources, scale = nodes, 1.0
    else:
        sources = sorted(nodes, key=lambda v: (-len(adj[v]), v))[:pivots]
        scale = len(nodes) / pivots
    for s in sources:
        stack: list[int] = []
        preds: dict[int, list[int]] = {v: [] for v in nodes}
        sigma = dict.fromkeys(nodes, 0.0)  # shortest-path counts
        dist = dict.fromkeys(nodes, -1)
        sigma[s], dist[s] = 1.0, 0
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for u in sorted(adj[v]):
                if dist[u] < 0:
                    dist[u] = dist[v] + 1
                    queue.append(u)
                if dist[u] == dist[v] + 1:
                    sigma[u] += sigma[v]
                    preds[u].append(v)
        # dependency accumulation, farthest-first
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            u = stack.pop()
            for v in preds[u]:
                delta[v] += sigma[v] / sigma[u] * (1.0 + delta[u])
            if u != s:
                bt[u] += delta[u] * scale
    return {v: b / 2.0 for v, b in bt.items()}  # undirected paths counted twice


def suggest_links(adj: Adjacency, *, top: int = 10, min_common: int = 2,
                  ) -> list[tuple[int, int, int]]:
    """Non-adjacent pairs ranked by shared-neighbor count ("connections you
    haven't drawn yet").
    # ponytail: O(V²) pair scan — LSH blocking (roadmap C1) when the graph is huge
    """
    nodes = sorted(adj)
    out: list[tuple[int, int, int]] = []
    neighbor_sets = {v: set(adj[v]) for v in nodes}
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if b in adj[a]:
                continue
            common = len(neighbor_sets[a] & neighbor_sets[b])
            if common >= min_common:
                out.append((a, b, common))
    out.sort(key=lambda t: (-t[2], t[0], t[1]))
    return out[:top]
