import hashlib
import math
import re

from .base import Extraction, ExtractedNode, Relation, TopicMatch, Vector

_CAP = re.compile(r"\b([A-Z][a-zA-Z0-9]+)\b")


class FakeLLM:
    """Deterministic stand-in: capitalized words → entities, lowercase nouns → concepts.

    `same_topic` is scripted for resolver tests: `topic_decisions` maps a label pair
    (either order) to a verdict; unscripted pairs fall back to `default_same_topic`.
    """

    def __init__(self, *, topic_decisions: dict[tuple[str, str], bool] | None = None,
                 default_same_topic: bool = False):
        self._decisions = topic_decisions or {}
        self._default = default_same_topic

    def summarize(self, text: str) -> str:
        t = text.strip()
        return (t[:120] + "…") if len(t) > 120 else t

    def extract(self, text: str, *, abstraction: str = "balanced",
                interests=(), avoid=()) -> Extraction:
        caps = list(dict.fromkeys(_CAP.findall(text)))
        entities = [ExtractedNode(name=w, kind="entity", type="thing",
                                  description=f"entity {w}") for w in caps[:5]]
        words = [w.lower() for w in re.findall(r"\b[a-z]{4,}\b", text)]
        concepts = [ExtractedNode(name=w, kind="concept", description=f"concept {w}")
                    for w in list(dict.fromkeys(words))[:5]]
        return Extraction(entities=entities, concepts=concepts)

    def relate(self, names: list[str], text: str) -> list[Relation]:
        rels = []
        for i in range(len(names) - 1):
            rels.append(Relation(src_name=names[i], dst_name=names[i + 1],
                                 type="uses", evidence="adjacent in fake extraction"))
        return rels

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        decided = self._decisions.get((label_a, label_b))
        if decided is None:
            decided = self._decisions.get((label_b, label_a))
        if decided is None:
            decided = self._default
        return TopicMatch(same_topic=decided,
                          canonical_topic=label_b if decided else None,
                          reason="scripted")


class FakeEmbedder:
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def embed(self, texts: list[str], *, kind: str) -> list[Vector]:
        out: list[Vector] = []
        for t in texts:
            h = hashlib.sha256((kind + "|" + t).encode()).digest()
            raw = [(h[i % len(h)] - 128) / 128.0 for i in range(self.dim)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            out.append([x / norm for x in raw])
        return out


class FakeVision:
    """Deterministic stand-in: returns canned text regardless of the image bytes.

    Mirrors FakeLLM/FakeEmbedder so pipeline tests can drive the visual path
    without a browser or a real vision model.
    """

    def __init__(self, text: str = "Photosynthesis converts light into energy."):
        self._text = text

    def describe_image(self, images: list[bytes], prompt: str) -> str:
        return self._text
