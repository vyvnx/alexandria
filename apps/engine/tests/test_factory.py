from alexandria_core.config import Settings
from alexandria_engine import factory
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder


def test_factory_returns_fake():
    s = Settings(_env_file=None, llm="fake")
    assert isinstance(factory.build_llm(s), FakeLLM)


def test_factory_builds_embedder_with_fixed_dim():
    s = Settings(_env_file=None, llm="fake")
    emb = factory.build_embedder(s, fake=True)
    assert isinstance(emb, FakeEmbedder)
    assert len(emb.embed(["x"], kind="document")[0]) == s.embed_dim


def test_factory_llm_dispatch_is_lazy():
    # openai/ollama are imported lazily so missing creds don't break "fake"
    s = Settings(_env_file=None, llm="openai", openai_api_key="sk-test")
    llm = factory.build_llm(s)
    assert llm.__class__.__name__ == "OpenAIProvider"
