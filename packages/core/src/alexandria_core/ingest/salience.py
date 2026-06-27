"""Salience ranking for extracted entities.

The extractor casts a wide net; the abstraction dial decides how many of those
entities are worth keeping. We score each entity per-source and keep the top
`cap`. Mention frequency is the dominant signal — it's what separates a subject
discussed at length (Canelo) from a name sitting in a "list of champions" table.
A smaller similarity term nudges entities that match what the source is about.
Concepts are not ranked here; the dial throttles the entity flood specifically.
"""

import math
import re

from ..providers.base import ExtractedNode, Vector

_FREQ_WEIGHT = 0.6
_SIM_WEIGHT = 0.4


def _cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _mention_count(name: str, text_lower: str) -> int:
    """Whole-word, case-insensitive occurrences of `name` in the text, so
    'Ali' isn't inflated by 'Alice' or 'realign'."""
    if not name.strip():
        return 0
    return len(re.findall(rf"\b{re.escape(name.lower())}\b", text_lower))


def _minmax(values: list[float]) -> list[float]:
    """Scale to [0, 1]; an all-equal list collapses to 0 so the term drops out."""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return [0.0 for _ in values]
    return [(v - lo) / span for v in values]


def rank_entities(entities: list[ExtractedNode], vectors: list[Vector],
                  source_vec: Vector, text: str, cap: int | None,
                  ) -> tuple[list[ExtractedNode], list[Vector]]:
    """Keep the `cap` most salient entities, preserving their source order.

    `cap` of None (or >= the number of entities) returns everything unchanged.
    salience = 0.6 * minmax(log1p(mention_count)) + 0.4 * cosine(vec, source_vec).
    """
    if cap is None or cap >= len(entities):
        return list(entities), list(vectors)

    text_lower = text.lower()
    freqs = [math.log1p(_mention_count(e.name, text_lower)) for e in entities]
    freq_norm = _minmax(freqs)
    scores = [
        _FREQ_WEIGHT * f + _SIM_WEIGHT * _cosine(v, source_vec)
        for f, v in zip(freq_norm, vectors)
    ]

    # Pick the top `cap` by score, breaking ties toward earlier items, then
    # restore source order among the survivors.
    order = sorted(range(len(entities)), key=lambda i: (-scores[i], i))
    keep = sorted(order[:cap])
    return [entities[i] for i in keep], [vectors[i] for i in keep]
