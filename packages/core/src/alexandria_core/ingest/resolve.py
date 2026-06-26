import math
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from ..config import Settings
from ..graph.store import GraphStore
from ..graph.models import KIND_ENTITY, KIND_CONCEPT
from ..providers.base import ExtractedNode, LLMProvider, Vector

_KIND = {"entity": KIND_ENTITY, "concept": KIND_CONCEPT}
_ARTICLES = {"the", "a", "an"}
_KNN_K = 5


@dataclass
class Resolution:
    extracted: ExtractedNode
    vector: Vector
    existing_id: int | None = None      # matched an existing stored node
    batch_canonical: int | None = None  # matched an earlier item in this same batch (index)


def canonical_name(name: str) -> str:
    """Order-independent identity key: lowercase, strip possessives + punctuation,
    fold light plurals, drop articles, sort tokens. Possessives, plurals, word order
    and articles all collapse to the same key."""
    s = name.lower()
    s = re.sub(r"'s\b", "", s)         # possessive: dijkstra's -> dijkstra
    s = re.sub(r"s'\b", "s", s)        # plural possessive: algorithms' -> algorithms
    s = re.sub(r"[^\w\s]", " ", s)     # strip remaining punctuation
    tokens = []
    for tok in s.split():
        if tok in _ARTICLES:
            continue
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]             # light singular/plural fold
        tokens.append(tok)
    return " ".join(sorted(tokens))


def _cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class _Cand:
    cosine: float
    name: str
    existing_id: int | None = None     # a stored node
    batch_index: int | None = None     # an earlier item in this batch


def resolve(store: GraphStore, extracted: list[ExtractedNode], vectors: list[Vector],
            *, settings: Settings, llm: LLMProvider | None = None) -> list[Resolution]:
    """Resolve each extracted node against a unified pool (store + earlier batch items)
    via a cheapest→costliest cascade: canonical name → fuzzy/embedding → LLM gray zone."""
    merge_t = settings.merge_threshold
    amb_t = settings.ambiguous_threshold
    fuzzy_r = settings.fuzzy_ratio

    # Stage 1 index: {canonical name -> node}, built once over store entity/concept nodes.
    store_nodes = [n for n in store.all_nodes() if n.kind in (KIND_ENTITY, KIND_CONCEPT)]
    canon_to_store: dict[str, object] = {}
    for n in store_nodes:
        canon_to_store.setdefault(canonical_name(n.name), n)

    out: list[Resolution] = []
    batch: list[dict] = []                  # earlier resolved items (in-memory half of the pool)
    batch_by_canon: dict[str, int] = {}     # canonical -> earliest batch index

    for i, (node, vec) in enumerate(zip(extracted, vectors)):
        kind = _KIND.get(node.kind, KIND_CONCEPT)
        canon = canonical_name(node.name)
        res = Resolution(extracted=node, vector=vec)

        # ---- Stage 1: exact canonical match (kind-agnostic, free) ----
        store_hit = canon_to_store.get(canon)
        if store_hit is not None:
            res.existing_id = store_hit.id
        elif canon in batch_by_canon:
            res.batch_canonical = batch_by_canon[canon]
        else:
            # ---- Stage 2 + 3: fuzzy/embedding propose; embedding or LLM decides ----
            cand = _best_candidate(store, store_nodes, kind, canon, vec, fuzzy_r, amb_t, batch)
            if cand is not None:
                if cand.cosine >= merge_t:
                    _apply(res, cand)                      # auto-merge
                elif cand.cosine >= amb_t and llm is not None and \
                        llm.same_topic(node.name, cand.name).same_topic:
                    _apply(res, cand)                      # gray zone — LLM said same

        out.append(res)
        batch.append({"canon": canon, "name": node.name, "kind": kind, "vec": vec, "index": i})
        batch_by_canon.setdefault(canon, i)
    return out


def _apply(res: Resolution, cand: _Cand) -> None:
    if cand.existing_id is not None:
        res.existing_id = cand.existing_id
    else:
        res.batch_canonical = cand.batch_index


def _best_candidate(store: GraphStore, store_nodes, kind: str, canon: str, vec: Vector,
                    fuzzy_r: int, amb_t: float, batch: list[dict]) -> _Cand | None:
    cands: list[_Cand] = []

    # Embedding neighbours from the store (cosine comes straight from knn).
    knn_cos = dict(store.knn(vec, _KNN_K))
    for n in store_nodes:
        if n.kind != kind:                 # Stage 3 is kind-aware; cross-kind only via Stage 1
            continue
        cos = knn_cos.get(n.id)
        if cos is None and fuzz.token_set_ratio(canon, canonical_name(n.name)) >= fuzzy_r:
            # Stage 2: fuzzy name proposes a candidate knn didn't surface; score it directly.
            emb = store.get_embedding(n.id)
            if emb is not None:
                cos = _cosine(vec, emb)
        if cos is not None:
            cands.append(_Cand(cosine=cos, name=n.name, existing_id=n.id))

    # Earlier items in this same batch (the in-memory half of the unified pool).
    for b in batch:
        if b["kind"] != kind:
            continue
        cos = _cosine(vec, b["vec"])
        if cos >= amb_t or fuzz.token_set_ratio(canon, b["canon"]) >= fuzzy_r:
            cands.append(_Cand(cosine=cos, name=b["name"], batch_index=b["index"]))

    if not cands:
        return None
    return max(cands, key=lambda c: c.cosine)   # one decision, on the strongest candidate
