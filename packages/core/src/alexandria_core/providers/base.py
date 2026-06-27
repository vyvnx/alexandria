from dataclasses import dataclass, field
from typing import Protocol, Literal

Vector = list[float]


@dataclass
class ExtractedNode:
    name: str
    kind: str                 # "entity" | "concept"
    description: str = ""
    type: str | None = None   # entity subtype: person/org/tool/paper/... ; None for concepts


@dataclass
class Extraction:
    entities: list[ExtractedNode] = field(default_factory=list)
    concepts: list[ExtractedNode] = field(default_factory=list)


@dataclass
class Relation:
    src_name: str
    dst_name: str
    type: str                 # one of TYPED_EDGES (the pipeline adds mentions/about itself)
    evidence: str = ""


@dataclass
class TopicMatch:
    """Verdict of the gray-zone topic deduplication classifier."""
    same_topic: bool
    canonical_topic: str | None = None
    reason: str = ""


class LLMProvider(Protocol):
    def summarize(self, text: str) -> str: ...
    def extract(self, text: str, *, abstraction: str = "balanced") -> Extraction: ...
    def relate(self, names: list[str], text: str) -> list[Relation]: ...
    # Gray-zone resolver adjudicator: are two labels the same topic? (low-temp, JSON).
    def same_topic(self, label_a: str, label_b: str) -> TopicMatch: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], *, kind: Literal["query", "document"]) -> list[Vector]: ...
