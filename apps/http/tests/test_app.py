import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from alexandria_core.graph.store import GraphStore
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder
from alexandria_core.config import Settings
from alexandria_core.graph.models import KIND_CONCEPT


@pytest.fixture
def client():
    store = GraphStore(":memory:")
    store.init_schema()
    app = create_app(store=store, llm=FakeLLM(), embedder=FakeEmbedder(),
                     settings=Settings(_env_file=None, llm="fake",
                                       executions_db_path=":memory:"))
    return TestClient(app), store


def _ingest(c, **body):
    """POST an ingest and return the finished job's result. Ingest runs in a
    background task, which TestClient drives to completion before the POST
    returns — so one status GET already sees the job done."""
    job_id = c.post("/ingest", json=body).json()["job_id"]
    job = c.get(f"/ingest/{job_id}").json()
    assert job["status"] == "done", job
    return job["result"]


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
        "extraction_abstraction": "balanced",
    }


def test_config_reflects_overridden_settings():
    store = GraphStore(":memory:")
    store.init_schema()
    settings = Settings(
        _env_file=None, llm="fake", executions_db_path=":memory:",
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
    res = _ingest(c, note="Attention mechanisms power transformers.")
    assert res["source_id"] > 0

    g = c.get("/graph").json()
    assert len(g["nodes"]) >= 1
    assert all({"id", "kind", "name"} <= set(n) for n in g["nodes"])

    s = c.get("/search", params={"q": "attention"}).json()
    assert isinstance(s, list)


def test_graph_nodes_are_trimmed(client):
    # B1: /graph ships no data blob — the inspector lazy-loads it via /node/{id}
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers.")
    nodes = c.get("/graph").json()["nodes"]
    assert nodes and all(set(n) == {"id", "kind", "name"} for n in nodes)


def test_node_detail_keeps_data(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    assert "data" in c.get(f"/node/{sid}").json()["node"]


def test_node_detail(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    d = c.get(f"/node/{sid}").json()
    assert d["node"]["id"] == sid
    assert "neighbors" in d


def test_ingest_status_unknown_job_404(client):
    c, _ = client
    assert c.get("/ingest/nope").status_code == 404


def test_ingest_job_reports_failure_stage(client, monkeypatch):
    c, _ = client

    def _boom(*a, **kw):
        kw["on_stage"]("embedding")  # advance a stage, then fail mid-run
        raise RuntimeError("kaboom")

    monkeypatch.setattr("api.app.ingest", _boom)
    job_id = c.post("/ingest", json={"note": "n"}).json()["job_id"]
    job = c.get(f"/ingest/{job_id}").json()
    assert job["status"] == "failed"
    assert job["stage"] == "embedding"  # last stage retained
    assert "see server logs" in job["error"]


def test_ingest_requires_input(client):
    c, _ = client
    r = c.post("/ingest", json={})
    assert r.status_code == 400


def test_ingest_accepts_abstraction_level(client):
    c, _ = client
    r = c.post("/ingest", json={"note": "A boxing essay.", "abstraction": "abstract"})
    assert r.status_code == 200


def test_ingest_rejects_unknown_abstraction(client):
    c, _ = client
    r = c.post("/ingest", json={"note": "x", "abstraction": "nope"})
    assert r.status_code == 422


def test_ingest_passes_visual_flag_to_pipeline(client, monkeypatch):
    from dataclasses import dataclass
    c, _ = client
    seen = {}

    @dataclass
    class _Res:
        source_id: int = 1
        title: str = "t"
        summary: str = "s"
        nodes_added: int = 0
        nodes_reused: int = 0
        typed_edges_added: int = 0
        similar_edges_added: int = 0
        node_ids: tuple = ()

    def _spy(*a, **kw):
        seen.update(kw)
        return _Res()

    monkeypatch.setattr("api.app.ingest", _spy)
    r = c.post("/ingest", json={"note": "n", "visual": True})
    assert r.status_code == 200
    assert seen["visual"] is True


def test_ingest_visual_defaults_false(client, monkeypatch):
    from dataclasses import dataclass
    c, _ = client
    seen = {}

    @dataclass
    class _Res:
        source_id: int = 1
        title: str = "t"
        summary: str = "s"
        nodes_added: int = 0
        nodes_reused: int = 0
        typed_edges_added: int = 0
        similar_edges_added: int = 0
        node_ids: tuple = ()

    def _spy(*a, **kw):
        seen.update(kw)
        return _Res()

    monkeypatch.setattr("api.app.ingest", _spy)
    r = c.post("/ingest", json={"note": "n"})
    assert r.status_code == 200
    assert seen["visual"] is False


def test_executions_empty(client):
    c, _ = client
    assert c.get("/executions").json() == []


def test_executions_after_ingest(client):
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers.")
    rows = c.get("/executions").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "note"
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None
    # the fake pipeline exercised the metered seam per task
    assert {"summarize", "extract", "embed"} <= set(row["tasks"])
    assert row["tasks"]["summarize"]["calls"] == 1


def test_executions_records_failure(client, monkeypatch):
    c, _ = client

    def _boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("api.app.ingest", _boom)
    c.post("/ingest", json={"note": "n"})
    (row,) = c.get("/executions").json()
    assert row["status"] == "failed"


def test_dismiss_node(client):
    c, store = client
    nid = store.add_node(KIND_CONCEPT, "Patreon")
    r = c.post(f"/node/{nid}/dismiss")
    assert r.status_code == 200
    assert r.json() == {"dismissed": "Patreon"}
    g = c.get("/graph").json()
    assert all(n["id"] != nid for n in g["nodes"])


def test_dismiss_unknown_node_404(client):
    c, _ = client
    assert c.post("/node/9999/dismiss").status_code == 404


def test_dismiss_source_node_400(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    assert c.post(f"/node/{sid}/dismiss").status_code == 400
