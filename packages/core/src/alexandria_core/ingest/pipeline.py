from dataclasses import dataclass

from ..config import Settings
from ..graph.store import GraphStore
from ..graph.models import KIND_SOURCE, KIND_ENTITY, KIND_CONCEPT
from ..graph import similarity
from ..logging_config import get_logger
from ..providers.base import LLMProvider, EmbeddingProvider
from .loaders import load_url
from .resolve import resolve

log = get_logger("ingest")


@dataclass
class IngestResult:
    source_id: int
    title: str
    summary: str
    nodes_added: int
    nodes_reused: int
    typed_edges_added: int
    similar_edges_added: int
    node_ids: list[int]


def ingest(store: GraphStore, llm: LLMProvider, embedder: EmbeddingProvider,
           settings: Settings, *, url=None, note=None, fetch=None) -> IngestResult:
    log.info("ingest start: url=%s note=%s", url or "-", "yes" if note else "no")

    # 1. Load
    doc = load_url(url, fetch=fetch) if url else None
    title = (doc.title if doc and doc.title else None) or (url or "Note")
    article = doc.text if doc else ""

    # 2. Assemble (keep article vs. my-take distinguishable)
    parts = []
    if article:
        parts.append("ARTICLE:\n" + article)
    if note:
        parts.append("MY TAKE:\n" + note)
    combined = "\n\n".join(parts) or title

    # 3. Summarize
    summary = llm.summarize(combined)
    log.debug("summarized (%d chars in, %d chars out)", len(combined), len(summary))

    # 4. Extract
    extraction = llm.extract(combined)
    extracted = list(extraction.entities) + list(extraction.concepts)
    log.info("extracted %d entities, %d concepts from %r",
             len(extraction.entities), len(extraction.concepts), title)
    if not extracted:
        log.warning("no entities or concepts extracted from %r — graph unchanged", title)

    # 5. Embed (source + each extracted node — name + description)
    src_vec = embedder.embed([combined], kind="document")[0]
    node_texts = [f"{n.name}. {n.description}".strip() for n in extracted]
    node_vecs = embedder.embed(node_texts, kind="document") if node_texts else []
    log.debug("embedded source + %d nodes", len(node_vecs))

    # source node first (always new)
    source_id = store.add_node(KIND_SOURCE, title, {"description": summary})
    store.add_source(source_id, url=url, author=(doc.author if doc else None),
                     published_at=(doc.published_at if doc else None),
                     raw_text=article, my_note=note, summary=summary)
    store.add_embedding(source_id, src_vec)

    # 6. Resolve extracted nodes against the store and within this batch.
    #    Uses merge/ambiguous/fuzzy knobs; the LLM is consulted only for the gray band.
    resolutions = resolve(store, extracted, node_vecs, settings=settings, llm=llm)

    # 9a. Persist new nodes (or reuse) — build name -> id map
    name_to_id: dict[str, int] = {}
    nodes_added = nodes_reused = 0
    new_node_ids: list[int] = []
    for r in resolutions:
        if r.existing_id is not None:
            nid = r.existing_id
            nodes_reused += 1
        elif r.batch_canonical is not None:
            nid = name_to_id[resolutions[r.batch_canonical].extracted.name]
        else:
            kind = KIND_ENTITY if r.extracted.kind == "entity" else KIND_CONCEPT
            data = {"description": r.extracted.description}
            if r.extracted.type:
                data["type"] = r.extracted.type
            nid = store.add_node(kind, r.extracted.name, data)
            store.add_embedding(nid, r.vector)
            nodes_added += 1
            new_node_ids.append(nid)
        name_to_id[r.extracted.name] = nid

    touched_ids = list(dict.fromkeys([source_id, *name_to_id.values()]))

    # 7. Relate — source -> node (mentions/about) + node <-> node typed edges
    typed_edges = 0
    for r in resolutions:
        nid = name_to_id[r.extracted.name]
        etype = "about" if r.extracted.kind == "concept" else "mentions"
        if store.add_edge(source_id, nid, etype, evidence="extracted from source",
                          from_source_id=source_id) is not None:
            typed_edges += 1
    for rel in llm.relate(list(name_to_id.keys()), combined):
        if rel.src_name in name_to_id and rel.dst_name in name_to_id:
            if store.add_edge(name_to_id[rel.src_name], name_to_id[rel.dst_name], rel.type,
                              evidence=rel.evidence, from_source_id=source_id) is not None:
                typed_edges += 1

    # 8. Similar — top-k per newly added node
    similar_edges = 0
    for nid in new_node_ids:
        vec = next(r.vector for r in resolutions if name_to_id.get(r.extracted.name) == nid)
        for other_id, score in similarity.top_k_similar(
                store, nid, vec, settings.similar_top_k, settings.similar_threshold):
            if store.add_edge(nid, other_id, "similar-to", weight=round(score, 4),
                              from_source_id=source_id) is not None:
                similar_edges += 1

    # 10. Log + return
    log.info("nodes: +%d new, %d reused", nodes_added, nodes_reused)
    log.info("edges: +%d typed, +%d similar", typed_edges, similar_edges)
    log.info("ingest done: source=%s %r (%d nodes touched)",
             source_id, title, len(touched_ids))
    store.log("ingest", f"source={source_id} +{nodes_added} nodes "
                        f"({nodes_reused} reused) +{typed_edges} typed +{similar_edges} similar")
    return IngestResult(source_id=source_id, title=title, summary=summary,
                        nodes_added=nodes_added, nodes_reused=nodes_reused,
                        typed_edges_added=typed_edges, similar_edges_added=similar_edges,
                        node_ids=touched_ids)
