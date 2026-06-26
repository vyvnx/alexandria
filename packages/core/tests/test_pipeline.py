import pytest

from alexandria_core.ingest.pipeline import ingest, IngestResult
from alexandria_core.graph.models import KIND_SOURCE

HTML = """<html><head><title>Transformers Paper</title></head><body><article>
<p>Transformers use attention. Vaswani introduced the architecture.</p>
</article></body></html>"""


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
