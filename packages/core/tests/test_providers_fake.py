from alexandria_core.providers.fake import FakeLLM, FakeEmbedder
from alexandria_core.providers.base import Extraction


def test_fake_llm_extract_is_deterministic():
    llm = FakeLLM()
    text = "Transformers use attention. Vaswani wrote the paper."
    e1 = llm.extract(text); e2 = llm.extract(text)
    assert isinstance(e1, Extraction)
    assert [n.name for n in e1.entities] == [n.name for n in e2.entities]
    assert e1.entities or e1.concepts   # something extracted


def test_fake_llm_relate_uses_known_names():
    llm = FakeLLM()
    rels = llm.relate(["A", "B"], "A extends B")
    assert all(r.src_name in {"A", "B"} and r.dst_name in {"A", "B"} for r in rels)


def test_fake_embedder_dim_and_determinism():
    emb = FakeEmbedder(dim=1024)
    v1 = emb.embed(["hello"], kind="document")[0]
    v2 = emb.embed(["hello"], kind="document")[0]
    assert len(v1) == 1024 and v1 == v2
    assert emb.embed(["other"], kind="document")[0] != v1
