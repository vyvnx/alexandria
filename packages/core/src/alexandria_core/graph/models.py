from dataclasses import dataclass, field

KIND_SOURCE, KIND_ENTITY, KIND_CONCEPT = "source", "entity", "concept"
TYPED_EDGES = {"mentions", "about", "uses", "extends", "contradicts", "authored-by"}
SEMANTIC_EDGE = "similar-to"
SYMMETRIC_EDGES = {"similar-to", "contradicts"}


@dataclass
class Node:
    id: int | None
    kind: str          # KIND_SOURCE | KIND_ENTITY | KIND_CONCEPT
    name: str
    data: dict = field(default_factory=dict)   # entity.type, description, etc.
    created_at: str | None = None


@dataclass
class Edge:
    id: int | None
    src_id: int
    dst_id: int
    type: str
    weight: float | None = None        # cosine score for similar-to; None for typed
    evidence: str | None = None
    from_source_id: int | None = None
    created_at: str | None = None
