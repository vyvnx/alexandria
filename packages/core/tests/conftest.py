import pytest

from alexandria_core.config import Settings


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm="fake", db_path=":memory:")


@pytest.fixture
def built():
    from alexandria_core.graph.store import GraphStore
    from alexandria_core.providers.fake import FakeLLM, FakeEmbedder

    s = GraphStore(":memory:")
    s.init_schema()
    yield {
        "store": s, "llm": FakeLLM(), "embedder": FakeEmbedder(),
        "settings": Settings(_env_file=None, llm="fake"),
    }
    s.close()
