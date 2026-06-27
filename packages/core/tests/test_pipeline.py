import pytest

from alexandria_core.ingest.pipeline import ingest, IngestResult
from alexandria_core.graph.models import KIND_SOURCE, KIND_ENTITY, KIND_CONCEPT
from alexandria_core.graph.store import GraphStore
from alexandria_core.providers.base import Extraction, ExtractedNode, TopicMatch
from alexandria_core.providers.fake import FakeEmbedder
from alexandria_core.config import Settings

HTML = """<html><head><title>Transformers Paper</title></head><body><article>
<p>Transformers use attention. Vaswani introduced the architecture.</p>
</article></body></html>"""


class _ManyLLM:
    """Emits a fixed number of distinct entities + concepts, ignoring the text —
    so we can exercise the salience cap end-to-end."""

    def __init__(self, n_entities: int, n_concepts: int):
        self.n_entities, self.n_concepts = n_entities, n_concepts

    def summarize(self, text):
        return text[:40]

    def extract(self, text, *, abstraction="balanced"):
        ents = [ExtractedNode(f"Fighter{i}", "entity", f"fighter {i}", "person")
                for i in range(self.n_entities)]
        cons = [ExtractedNode(f"idea{i}", "concept", f"idea {i}")
                for i in range(self.n_concepts)]
        return Extraction(entities=ents, concepts=cons)

    def relate(self, names, text):
        return []

    def same_topic(self, a, b):
        return TopicMatch(same_topic=False)


def _kind_count(store, kind):
    return sum(1 for n in store.all_nodes() if n.kind == kind)


def test_abstract_caps_entities_but_leaves_concepts():
    store = GraphStore(":memory:")
    store.init_schema()
    settings = Settings(_env_file=None, llm="fake")  # abstract cap = 5
    ingest(store, _ManyLLM(8, 4), FakeEmbedder(), settings,
           note="boxing essay", fetch=lambda u: None, abstraction="abstract")
    assert _kind_count(store, KIND_ENTITY) == settings.extract_entity_cap_abstract
    assert _kind_count(store, KIND_CONCEPT) == 4
    store.close()


def test_exhaustive_keeps_every_entity():
    store = GraphStore(":memory:")
    store.init_schema()
    settings = Settings(_env_file=None, llm="fake")
    ingest(store, _ManyLLM(8, 2), FakeEmbedder(), settings,
           note="boxing essay", fetch=lambda u: None, abstraction="exhaustive")
    assert _kind_count(store, KIND_ENTITY) == 8
    store.close()


def test_abstraction_defaults_to_settings_when_unspecified():
    store = GraphStore(":memory:")
    store.init_schema()
    settings = Settings(_env_file=None, llm="fake", extraction_abstraction="abstract")
    ingest(store, _ManyLLM(8, 0), FakeEmbedder(), settings,
           note="x", fetch=lambda u: None)  # no abstraction arg
    assert _kind_count(store, KIND_ENTITY) == settings.extract_entity_cap_abstract
    store.close()


def test_ingest_builds_graph(built):
    if not built["store"].vec_available:
        pytest.skip("sqlite-vec required for similar-to edges")
    res = ingest(built["store"], built["llm"], built["embedder"], built["settings"],
                 url="http://x/paper", note="I think attention generalizes.",
                 fetch=lambda u: HTML)
    assert isinstance(res, IngestResult)
    assert res.source_id > 0
    src = built["store"].get_node(res.source_id)
    assert src.kind == KIND_SOURCE
    # the source got entity/concept nodes + edges
    assert res.nodes_added >= 1
    assert res.typed_edges_added >= 1
    # the user's note is stored first-class
    assert built["store"].get_source(res.source_id)["my_note"].startswith("I think")


def test_ingest_reuses_existing_nodes(built):
    if not built["store"].vec_available:
        pytest.skip("sqlite-vec required")
    s = built
    ingest(s["store"], s["llm"], s["embedder"], s["settings"], url="http://a", note=None, fetch=lambda u: HTML)
    n_before = len(s["store"].all_nodes())
    res2 = ingest(s["store"], s["llm"], s["embedder"], s["settings"], url="http://b", note=None, fetch=lambda u: HTML)
    # same content → most nodes reused, only the new source node is truly new
    assert res2.nodes_reused >= 1
    assert len(s["store"].all_nodes()) < n_before * 2


def test_ingest_note_only(built):
    res = ingest(built["store"], built["llm"], built["embedder"], built["settings"],
                 url=None, note="Eigenvalues describe stretch directions of a matrix.",
                 fetch=lambda u: None)
    assert res.source_id > 0
    assert res.summary != ""
