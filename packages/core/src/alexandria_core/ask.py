"""GraphRAG Q&A (roadmap D3) — answer from a connected subgraph, cited.

Retrieval is graph-shaped, not flat chunks: k-NN seeds from the question
embedding, expanded one hop along the graph's edges, so an answer draws on a
*connected* neighborhood — sources and the concepts that tie them together.
Each retrieved node becomes one numbered passage; the provider's `answer`
method synthesizes a reply citing passages as [n].
"""
from __future__ import annotations

from .graph.models import KIND_SOURCE
from .logging_config import get_logger

log = get_logger("ask")


def retrieve(store, embedder, question: str, *, seeds: int = 5, hops: int = 1,
             max_passages: int = 12) -> list[dict]:
    """Numbered context passages for a question: knn seeds (name-match
    fallback without sqlite-vec) expanded `hops` along the graph."""
    seed_ids: list[int] = []
    if store.vec_available:
        qvec = embedder.embed([question], kind="query")[0]
        seed_ids = [nid for nid, _ in store.knn(qvec, seeds)]
    if not seed_ids:  # no vectors (or extension missing): fall back to names
        needle = question.lower()
        seed_ids = [n.id for n in store.all_nodes()
                    if any(w in n.name.lower() for w in needle.split()) ][:seeds]

    ordered: list[int] = []
    for sid in seed_ids:
        for nid in [sid, *store.reach(sid, hops)]:
            if nid not in ordered:
                ordered.append(nid)

    passages = []
    for nid in ordered[:max_passages]:
        node = store.get_node(nid)
        if node is None:
            continue
        if node.kind == KIND_SOURCE:
            src = store.get_source(nid) or {}
            text = src.get("summary") or (src.get("raw_text") or "")[:400]
        else:
            parts = [node.data.get("description", "") if node.data else ""]
            parts += [e.evidence for e in store.edges_for(nid) if e.evidence]
            text = "; ".join(p for p in parts if p)[:400]
        if not text:
            continue
        passages.append({"n": len(passages) + 1, "node_id": nid,
                         "name": node.name, "text": text})
    return passages


def ask(store, embedder, llm, settings, question: str) -> dict:
    passages = retrieve(store, embedder, question)
    if not passages:
        return {"answer": "There is nothing in the graph about that yet — "
                          "chart some sources first.",
                "citations": [], "passages": 0}
    context = "\n".join(f"[{p['n']}] {p['name']}: {p['text']}" for p in passages)
    answer = llm.answer(question, context)
    log.info("ask %r -> %d passages, %d chars", question, len(passages), len(answer))
    return {"answer": answer,
            "citations": [{"n": p["n"], "node_id": p["node_id"], "name": p["name"]}
                          for p in passages],
            "passages": len(passages)}
