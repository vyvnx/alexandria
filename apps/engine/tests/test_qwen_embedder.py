import pytest

from engine.qwen_embedder import Qwen3Embedder, format_for_kind


def test_query_gets_instruction_wrapper():
    q = format_for_kind("vector search", kind="query")
    assert q.startswith("Instruct:") and "Query: vector search" in q


def test_document_is_raw():
    assert format_for_kind("plain doc", kind="document") == "plain doc"


@pytest.mark.integration
def test_real_model_embeds_to_fixed_dim():
    emb = Qwen3Embedder(model_name="Qwen/Qwen3-Embedding-0.6B", dim=1024)
    v = emb.embed(["hello world"], kind="document")[0]
    assert len(v) == 1024
