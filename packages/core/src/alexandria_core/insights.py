"""Structural insights (roadmap D2) — what the graph knows about itself.

Composes the hand-rolled algo core over the live store: PageRank ranks your
strongest interests, Louvain finds emergent topic communities, betweenness
surfaces the serendipity bridges between them, common-neighbor prediction
proposes connections you haven't drawn, the short-half-life interest pool
shows what you keep circling lately, and `contradicts` edges become the lint
list. All computed on demand.
# ponytail: recomputed per request — cache when a real graph makes it slow
"""
from __future__ import annotations

from .algo import betweenness, build_adjacency, louvain, pagerank, suggest_links
from .graph.models import KIND_SOURCE

_TOP = 10


def compute_insights(store, settings) -> dict:
    nodes = {n.id: n for n in store.all_nodes()}
    edges = store.all_edges()
    adj = build_adjacency(store)

    pr = pagerank(adj)
    non_source = [nid for nid in pr if nodes[nid].kind != KIND_SOURCE]

    strongest = [
        {"id": nid, "name": nodes[nid].name, "kind": nodes[nid].kind,
         "score": round(pr[nid], 5)}
        for nid in sorted(non_source, key=lambda i: -pr[i])[:_TOP]
    ]

    comm = louvain(adj)
    members: dict[int, list[int]] = {}
    for nid, c in comm.items():
        if nodes[nid].kind != KIND_SOURCE:
            members.setdefault(c, []).append(nid)
    communities = []
    for c, ids in sorted(members.items(), key=lambda kv: -len(kv[1])):
        top = sorted(ids, key=lambda i: -pr[i])[:3]
        communities.append({"id": c, "size": len(ids),
                            "label": " · ".join(nodes[i].name for i in top)})

    bt = betweenness(adj)
    bridges = [
        {"id": nid, "name": nodes[nid].name, "score": round(bt[nid], 4)}
        for nid in sorted(non_source, key=lambda i: -bt[i])[:_TOP]
        if bt[nid] > 0
    ]

    # suggest between non-source nodes only — a source's fan-out is not a
    # meaningful shared-neighbor signal
    concept_adj = build_adjacency(
        store, include_kinds={k for k in {n.kind for n in nodes.values()}} - {KIND_SOURCE})
    suggestions = [
        {"a": {"id": a, "name": nodes[a].name},
         "b": {"id": b, "name": nodes[b].name}, "common": common}
        for a, b, common in suggest_links(concept_adj, top=_TOP)
    ]

    trending = [
        {"name": name, "weight": round(w, 3)}
        for name, w, _ in store.interest_pool(half_life_days=7.0, min_weight=1.0)[:_TOP]
    ]

    contradictions = [
        {"a": nodes[e.src_id].name, "b": nodes[e.dst_id].name,
         "evidence": e.evidence or ""}
        for e in edges if e.type == "contradicts"
        and e.src_id in nodes and e.dst_id in nodes
    ]

    return {
        "stats": {"nodes": len(nodes), "edges": len(edges)},
        "strongest_interests": strongest,
        "communities": communities,
        "bridges": bridges,
        "suggested_connections": suggestions,
        "trending": trending,
        "contradictions": contradictions,
    }
