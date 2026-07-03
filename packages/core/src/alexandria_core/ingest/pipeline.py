from dataclasses import dataclass

from ..config import Settings
from ..graph.store import GraphStore
from ..graph.models import KIND_SOURCE, KIND_ENTITY, KIND_CONCEPT
from ..graph import similarity
from ..logging_config import get_logger
from ..providers.base import LLMProvider, EmbeddingProvider
from .loaders import load_url
from .render import screenshot as _screenshot
from .resolve import resolve
from .salience import rank_entities

log = get_logger("ingest")

VISION_PROMPT = (
    "You are reading screenshots of a web page. Transcribe any tables as markdown "
    "and describe charts, figures, and infographics in prose. Report only the page's "
    "content; ignore navigation, ads, and boilerplate. If there is no meaningful "
    "visual content, reply with nothing."
)


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
           settings: Settings, *, url=None, note=None, fetch=None,
           abstraction=None, visual: bool = False, vision=None,
           render_fn=None) -> IngestResult:
    level = abstraction or settings.extraction_abstraction
    log.info("ingest start: url=%s note=%s abstraction=%s",
             url or "-", "yes" if note else "no", level)

    # 1. Load
    doc = load_url(url, fetch=fetch) if url else None
    title = (doc.title if doc and doc.title else None) or (url or "Note")
    article = doc.text if doc else ""

    # 1b. visual enrichment (opt-in): screenshot the page and let a vlm read the
    #     tables/charts/figures trafilatura drops. best-effort — any failure
    #     degrades to a text-only ingest.
    vlm_text = ""
    if visual and url and vision is not None:
        try:
            imgs = (render_fn or _screenshot)(url, settings=settings)
            vlm_text = vision.describe_image(imgs, VISION_PROMPT) if imgs else ""
        except Exception:
            log.warning("visual enrichment failed for %s — skipping", url)

    # 2. Assemble (keep article vs. my-take distinguishable)
    parts = []
    if article:
        parts.append("ARTICLE:\n" + article)
    if note:
        parts.append("MY TAKE:\n" + note)
    if vlm_text:
        parts.append("VISUAL CONTENT:\n" + vlm_text)
    combined = "\n\n".join(parts) or title

    # 3. Summarize
    summary = llm.summarize(combined)
    log.debug("summarized (%d chars in, %d chars out)", len(combined), len(summary))

    # 4. Extract (the abstraction level steers how selective the extractor is)
    extraction = llm.extract(combined, abstraction=level)
    entities = list(extraction.entities)
    concepts = list(extraction.concepts)
    log.info("extracted %d entities, %d concepts from %r",
             len(entities), len(concepts), title)

    # 5. Embed (source + each extracted node — name + description)
    src_vec = embedder.embed([combined], kind="document")[0]
    ent_texts = [f"{n.name}. {n.description}".strip() for n in entities]
    con_texts = [f"{n.name}. {n.description}".strip() for n in concepts]
    ent_vecs = embedder.embed(ent_texts, kind="document") if ent_texts else []
    con_vecs = embedder.embed(con_texts, kind="document") if con_texts else []

    # 5a. Abstraction cap — keep only the most salient entities for this level.
    #     Concepts are left uncapped; the dial throttles the entity flood.
    cap = settings.entity_cap(level)
    n_before = len(entities)
    entities, ent_vecs = rank_entities(entities, ent_vecs, src_vec, combined, cap)
    if len(entities) < n_before:
        log.info("salience cap (%s): kept %d of %d entities", level, len(entities), n_before)

    extracted = entities + concepts
    node_vecs = ent_vecs + con_vecs
    log.debug("embedded source + %d nodes", len(node_vecs))
    if not extracted:
        log.warning("no entities or concepts extracted from %r — graph unchanged", title)

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
