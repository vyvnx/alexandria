"""Digests (roadmap D4) — "what your graph learned this week".

A structural summary of the window: what arrived, which newcomers matter
(pagerank), what you keep circling (short-half-life interest pool), and the
spaced-repetition half — high-value nodes nothing touched lately. The llm
narrative over it is opt-in at the endpoint; structure is always free.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .algo import build_adjacency, pagerank
from .graph.models import KIND_SOURCE

_TOP = 10
_RESURFACE = 5


def build_digest(store, settings, *, days: int = 7) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    nodes = {n.id: n for n in store.all_nodes()}
    edges = store.all_edges()
    pr = pagerank(build_adjacency(store))

    created = [n for n in nodes.values() if (n.created_at or "") >= cutoff]
    top_new = sorted((n for n in created if n.kind != KIND_SOURCE),
                     key=lambda n: -pr.get(n.id, 0.0))[:_TOP]

    touched: set[int] = set()
    for e in edges:
        if (e.created_at or "") >= cutoff:
            touched.update((e.src_id, e.dst_id))
    untouched = [nid for nid, n in nodes.items()
                 if n.kind != KIND_SOURCE and nid not in touched and pr.get(nid, 0) > 0]
    resurface = sorted(untouched, key=lambda i: -pr[i])[:_RESURFACE]

    return {
        "days": days,
        "new_sources": sum(1 for n in created if n.kind == KIND_SOURCE),
        "new_nodes": len(created),
        "top_new": [{"id": n.id, "name": n.name, "kind": n.kind,
                     "score": round(pr.get(n.id, 0.0), 5)} for n in top_new],
        "trending": [{"name": name, "weight": round(w, 3)}
                     for name, w, _ in store.interest_pool(
                         half_life_days=7.0, min_weight=1.0)[:_TOP]],
        "resurface": [{"id": nid, "name": nodes[nid].name,
                       "score": round(pr[nid], 5)} for nid in resurface],
        "contradictions": sum(1 for e in edges if e.type == "contradicts"),
    }


def render_digest(d: dict) -> str:
    """Plain-text rendering — the input for the optional llm narrative."""
    lines = [
        f"In the last {d['days']} days the graph gained {d['new_sources']} "
        f"sources and {d['new_nodes']} nodes.",
    ]
    if d["top_new"]:
        lines.append("Notable newcomers: "
                     + ", ".join(n["name"] for n in d["top_new"]) + ".")
    if d["trending"]:
        lines.append("Circling lately: "
                     + ", ".join(t["name"] for t in d["trending"]) + ".")
    if d["resurface"]:
        lines.append("Worth revisiting (important but untouched): "
                     + ", ".join(n["name"] for n in d["resurface"]) + ".")
    if d["contradictions"]:
        lines.append(f"{d['contradictions']} documented contradiction(s) to review.")
    return "\n".join(lines)
