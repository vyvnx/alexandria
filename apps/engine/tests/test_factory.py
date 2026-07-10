from alexandria_core.config import Settings
from engine import factory
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
    # openai is imported lazily so missing creds don't break "fake"
    s = Settings(_env_file=None, llm="openai", openai_api_key="sk-test")
    llm = factory.build_llm(s)
    assert llm.__class__.__name__ == "OpenAIProvider"


def test_factory_passes_base_url_to_openai_provider():
    s = Settings(_env_file=None, llm="openai", openai_api_key="sk",
                 openai_base_url="http://localhost:1234/v1")
    llm = factory.build_llm(s)
    assert str(llm.client.base_url).startswith("http://localhost:1234/v1")


def test_build_vision_fake_returns_fake_vision():
    from engine.factory import build_vision
    from alexandria_core.providers.fake import FakeVision
    from alexandria_core.config import Settings
    assert isinstance(build_vision(Settings(_env_file=None, llm="fake")), FakeVision)


def test_build_vision_openai_uses_vision_model():
    from engine.factory import build_vision
    from alexandria_core.config import Settings
    p = build_vision(Settings(_env_file=None, llm="openai",
                              openai_api_key="sk", openai_vision_model="gpt-4o"))
    assert p.model == "gpt-4o"
