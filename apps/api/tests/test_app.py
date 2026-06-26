import pytest
from fastapi.testclient import TestClient

from alexandria_api.app import create_app
from alexandria_core.graph.store import GraphStore
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder
from alexandria_core.config import Settings


@pytest.fixture
def client():
    store = GraphStore(":memory:")
    store.init_schema()
    app = create_app(store=store, llm=FakeLLM(), embedder=FakeEmbedder(),
                     settings=Settings(_env_file=None, llm="fake"))
    return TestClient(app), store


def test_healthz(client):
    c, _ = client
    r = c.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_config_returns_defaults(client):
    c, _ = client
    r = c.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "star_size_min": 4.0,
        "star_size_max": 11.0,
        "galaxy_resolution": 1.0,
        "min_galaxy_size": 3,
    }


def test_config_reflects_overridden_settings():
    store = GraphStore(":memory:")
    store.init_schema()
    settings = Settings(
        _env_file=None, llm="fake",
        star_size_min=2.0, star_size_max=20.0,
        galaxy_resolution=1.5, min_galaxy_size=5,
    )
    app = create_app(store=store, llm=FakeLLM(), embedder=FakeEmbedder(), settings=settings)
    c = TestClient(app)
    body = c.get("/config").json()
    assert body["star_size_min"] == 2.0
    assert body["star_size_max"] == 20.0
    assert body["galaxy_resolution"] == 1.5
    assert body["min_galaxy_size"] == 5


def test_ingest_note_then_graph_and_search(client):
    c, _ = client
    r = c.post("/ingest", json={"note": "Attention mechanisms power transformers."})
    assert r.status_code == 200
    body = r.json()
    assert body["source_id"] > 0

    g = c.get("/graph").json()
    assert len(g["nodes"]) >= 1
    assert all({"id", "kind", "name"} <= set(n) for n in g["nodes"])

    s = c.get("/search", params={"q": "attention"}).json()
    assert isinstance(s, list)


def test_node_detail(client):
    c, _ = client
    sid = c.post("/ingest", json={"note": "Graphs model relationships."}).json()["source_id"]
    d = c.get(f"/node/{sid}").json()
    assert d["node"]["id"] == sid
    assert "neighbors" in d


def test_ingest_requires_input(client):
    c, _ = client
    r = c.post("/ingest", json={})
    assert r.status_code == 400
