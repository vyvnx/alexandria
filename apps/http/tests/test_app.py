import time

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from alexandria_core.graph.store import GraphStore
from alexandria_core.intake import IntakeRegistry
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder
from alexandria_core.config import Settings
from alexandria_core.graph.models import KIND_CONCEPT


@pytest.fixture
def client(tmp_path):
    store = GraphStore(":memory:")
    store.init_schema()
    app = create_app(store=store, llm=FakeLLM(), embedder=FakeEmbedder(),
                     registry=IntakeRegistry(":memory:"),
                     settings=Settings(_env_file=None, llm="fake",
                                       executions_db_path=":memory:",
                                       upload_dir=str(tmp_path)))
    # context manager so the lifespan runs — it starts the ingest worker thread
    with TestClient(app) as c:
        yield c, store


def _wait(c, job_id, timeout=5.0):
    """Poll a queued ingest job until the worker finishes it (or timeout)."""
    deadline = time.time() + timeout
    while True:
        job = c.get(f"/api/ingest/{job_id}").json()
        if job["status"] != "running" or time.time() > deadline:
            return job
        time.sleep(0.02)


def _ingest(c, **body):
    """POST an ingest and return the finished job's result."""
    job_id = c.post("/api/ingest", json=body).json()["job_id"]
    job = _wait(c, job_id)
    assert job["status"] == "done", job
    return job["result"]


def test_healthz(client):
    c, _ = client
    r = c.get("/api/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_config_returns_defaults(client):
    c, _ = client
    r = c.get("/api/config")
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
    body = c.get("/api/config").json()
    assert body["star_size_min"] == 2.0
    assert body["star_size_max"] == 20.0
    assert body["galaxy_resolution"] == 1.5
    assert body["min_galaxy_size"] == 5


def test_ingest_note_then_graph_and_search(client):
    c, _ = client
    res = _ingest(c, note="Attention mechanisms power transformers.")
    assert res["source_id"] > 0

    g = c.get("/api/graph").json()
    assert len(g["nodes"]) >= 1
    assert all({"id", "kind", "name"} <= set(n) for n in g["nodes"])

    s = c.get("/api/search", params={"q": "attention"}).json()
    assert isinstance(s, list)


def test_graph_nodes_are_trimmed(client):
    # B1: /graph ships no data blob — the inspector lazy-loads it via /node/{id}
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers.")
    nodes = c.get("/api/graph").json()["nodes"]
    assert nodes and all(set(n) == {"id", "kind", "name"} for n in nodes)


def test_node_detail_keeps_data(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    assert "data" in c.get(f"/api/node/{sid}").json()["node"]


def test_node_detail(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    d = c.get(f"/api/node/{sid}").json()
    assert d["node"]["id"] == sid
    assert "neighbors" in d


def test_ingest_status_unknown_job_404(client):
    c, _ = client
    assert c.get("/api/ingest/nope").status_code == 404


def test_ingest_job_reports_failure_stage(client, monkeypatch):
    c, _ = client

    def _boom(*a, **kw):
        kw["on_stage"]("embedding")  # advance a stage, then fail mid-run
        raise RuntimeError("kaboom")

    monkeypatch.setattr("api.app.ingest", _boom)
    job_id = c.post("/api/ingest", json={"note": "n"}).json()["job_id"]
    job = _wait(c, job_id)
    assert job["status"] == "failed"
    assert job["stage"] == "embedding"  # last stage retained
    assert "see server logs" in job["error"]


def test_ingest_requires_input(client):
    c, _ = client
    r = c.post("/api/ingest", json={})
    assert r.status_code == 400


def test_ingest_accepts_abstraction_level(client):
    c, _ = client
    r = c.post("/api/ingest", json={"note": "A boxing essay.", "abstraction": "abstract"})
    assert r.status_code == 200


def test_ingest_rejects_unknown_abstraction(client):
    c, _ = client
    r = c.post("/api/ingest", json={"note": "x", "abstraction": "nope"})
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
    r = c.post("/api/ingest", json={"note": "n", "visual": True})
    assert r.status_code == 200
    _wait(c, r.json()["job_id"])
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
    r = c.post("/api/ingest", json={"note": "n"})
    assert r.status_code == 200
    _wait(c, r.json()["job_id"])
    assert seen["visual"] is False


def test_executions_empty(client):
    c, _ = client
    assert c.get("/api/executions").json() == []


def test_executions_after_ingest(client):
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers.")
    rows = c.get("/api/executions").json()
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
    job_id = c.post("/api/ingest", json={"note": "n"}).json()["job_id"]
    _wait(c, job_id)
    (row,) = c.get("/api/executions").json()
    assert row["status"] == "failed"


def test_job_row_carries_queue_to_done_timestamps(client):
    c, _ = client
    job_id = c.post("/api/ingest", json={"note": "Queued then done."}).json()["job_id"]
    assert _wait(c, job_id)["status"] == "done"
    (row,) = c.get("/api/executions").json()
    assert row["queued_at"] and row["started_at"] and row["finished_at"]
    assert row["queued_at"] <= row["started_at"] <= row["finished_at"]


def test_jobs_survive_in_one_persistent_store(client):
    # the queue is the execution table: the job POST /ingest created is the
    # same row GET /executions lists — no separate in-memory registry
    c, _ = client
    job_id = c.post("/api/ingest", json={"note": "One row, two views."}).json()["job_id"]
    _wait(c, job_id)
    assert any(str(r["id"]) == job_id for r in c.get("/api/executions").json())


def test_insights_after_ingests(client):
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers today.")
    _ingest(c, note="Attention improves retrieval models notably.")
    ins = c.get("/api/insights").json()
    assert ins["stats"]["nodes"] > 0 and ins["stats"]["edges"] > 0
    names = [i["name"] for i in ins["strongest_interests"]]
    assert "Attention" in names  # recurs across both notes → high pagerank
    assert ins["communities"]


def test_ask_answers_with_citations(client):
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers today.")
    res = c.get("/api/ask", params={"q": "what powers transformers?"}).json()
    assert res["answer"] and res["passages"] >= 1
    assert res["citations"] and all("name" in cit for cit in res["citations"])


def test_ask_requires_a_question(client):
    c, _ = client
    assert c.get("/api/ask").status_code == 400


def test_usage_rollup_after_ingest(client):
    c, _ = client
    _ingest(c, note="Attention mechanisms power transformers.")
    u = c.get("/api/usage").json()
    assert u["days"] == 30
    assert u["total_calls"] >= 3
    assert {"summarize", "extract", "embed"} <= set(u["per_task"])
    assert len(u["per_day"]) == 1
    assert u["per_source"][0]["source"] == "note"


class _PricedLLM(FakeLLM):
    """burns ~$1 of fake spend per summarize (at $1/M prompt tokens)"""

    def summarize(self, text):
        from alexandria_core.telemetry import add_usage
        add_usage(1_000_000, 0)
        return super().summarize(text)


def _budget_client(**settings_kw):
    store = GraphStore(":memory:")
    store.init_schema()
    app = create_app(store=store, llm=_PricedLLM(), embedder=FakeEmbedder(),
                     registry=IntakeRegistry(":memory:"),
                     settings=Settings(_env_file=None, llm="fake",
                                       executions_db_path=":memory:",
                                       price_in_per_mtok=1.0, **settings_kw))
    return TestClient(app)


def test_budget_hard_stop_defers_the_queue():
    with _budget_client(budget_daily_usd=0.5) as c:
        # first ingest runs (spend starts at 0) and blows the daily budget
        first = c.post("/api/ingest", json={"note": "first note"}).json()["job_id"]
        assert _wait(c, first)["status"] == "done"
        # second ingest stays queued — the worker defers while over budget
        second = c.post("/api/ingest", json={"note": "second note"}).json()["job_id"]
        time.sleep(0.8)  # a few worker ticks
        job = c.get(f"/api/ingest/{second}").json()
        assert job["status"] == "running" and job["stage"] == "queued"
        assert c.get("/api/usage").json()["budget"]["over"] == "daily"


def test_budget_with_fallback_keeps_processing():
    # a configured local fallback (F4) means over-budget flips models
    # instead of deferring the queue
    with _budget_client(budget_daily_usd=0.5,
                        fallback_base_url="http://localhost:9/v1") as c:
        for note in ("first note", "second note"):
            job = c.post("/api/ingest", json={"note": note}).json()["job_id"]
            assert _wait(c, job)["status"] == "done"
        assert c.get("/api/usage").json()["budget"]["over"] == "daily"


def test_no_budget_processes_everything():
    with _budget_client() as c:
        for note in ("first note", "second note"):
            job = c.post("/api/ingest", json={"note": note}).json()["job_id"]
            assert _wait(c, job)["status"] == "done"
        budget = c.get("/api/usage").json()["budget"]
        assert budget["over"] is None
        assert budget["spent_today_usd"] >= 2.0


def test_feeds_crud(client):
    c, _ = client
    r = c.post("/api/feeds", json={"url": "https://blog.example/rss", "cadence_minutes": 30})
    assert r.status_code == 200
    fid = r.json()["id"]
    (feed,) = c.get("/api/feeds").json()
    assert feed["url"] == "https://blog.example/rss"
    assert feed["cadence_minutes"] == 30
    assert feed["items"] == {"enqueued": 0, "filtered": 0, "error": 0}
    assert c.post("/api/feeds", json={"url": "https://blog.example/rss"}).status_code == 409
    assert c.post(f"/api/feeds/{fid}/poll").status_code == 200
    assert c.post("/api/feeds/999/poll").status_code == 404
    assert c.delete(f"/api/feeds/{fid}").status_code == 200
    assert c.get("/api/feeds").json() == []
    assert c.delete("/api/feeds/999").status_code == 404


def test_feed_poll_flows_through_the_queue(client, monkeypatch):
    c, store = client
    monkeypatch.setattr("alexandria_core.intake.discover_items",
                        lambda u: ["https://blog.example/post-1"])
    html = "<html><body><article><p>Attention mechanisms power transformers "
    html += "in modern language models today.</p></article></body></html>"
    # the poller loads the item once, the pipeline loads it again on ingest
    from alexandria_core.ingest import loaders, pipeline
    monkeypatch.setattr(loaders, "load_url",
                        lambda url, fetch=None: loaders.LoadedDoc(
                            url=url, title="Post 1", author=None,
                            published_at=None, text="Attention powers transformers."))
    monkeypatch.setattr(pipeline, "load_url", loaders.load_url)
    c.post("/api/feeds", json={"url": "https://blog.example/rss"})

    deadline = time.time() + 5
    while time.time() < deadline:
        rows = c.get("/api/executions").json()
        if rows and rows[0]["status"] == "succeeded":
            break
        time.sleep(0.05)
    (row,) = c.get("/api/executions").json()
    assert row["source"] == "https://blog.example/post-1"
    assert row["status"] == "succeeded"
    assert store.find_source_by_url("https://blog.example/post-1") is not None
    (feed,) = c.get("/api/feeds").json()
    assert feed["items"]["enqueued"] == 1


def test_topics_crud(client):
    c, _ = client
    r = c.post("/api/topics", json={"name": "cloud architecture", "weight": 2.0})
    assert r.status_code == 200
    tid = r.json()["id"]
    (topic,) = c.get("/api/topics").json()
    assert topic["name"] == "cloud architecture" and topic["weight"] == 2.0
    assert c.post("/api/topics", json={"name": "cloud architecture"}).status_code == 409
    assert c.delete(f"/api/topics/{tid}").status_code == 200
    assert c.get("/api/topics").json() == []
    assert c.delete("/api/topics/999").status_code == 404


def _pdf_bytes(text="Spaced repetition beats cramming, according to Ebbinghaus."):
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_upload_flows_through_the_queue(client):
    c, store = client
    pdf = _pdf_bytes()
    r = c.post("/api/ingest/file", files={"file": ("notes.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["title"] == "notes.pdf"
    assert store.get_source(job["result"]["source_id"])["raw_text"].startswith("Spaced")
    # the same bytes again dedup — no second source, no llm spend
    r2 = c.post("/api/ingest/file", files={"file": ("again.pdf", pdf, "application/pdf")})
    job2 = _wait(c, r2.json()["job_id"])
    assert job2["result"]["deduped"] is True
    assert job2["result"]["source_id"] == job["result"]["source_id"]


def test_textless_pdf_fails_with_actionable_error(client):
    c, _ = client
    r = c.post("/api/ingest/file", files={"file": ("scan.pdf", b"not a pdf", "application/pdf")})
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "failed"
    assert "ocr" in job["error"].lower()


def test_dismiss_node(client):
    c, store = client
    nid = store.add_node(KIND_CONCEPT, "Patreon")
    r = c.post(f"/api/node/{nid}/dismiss")
    assert r.status_code == 200
    assert r.json() == {"dismissed": "Patreon"}
    g = c.get("/api/graph").json()
    assert all(n["id"] != nid for n in g["nodes"])


def test_dismiss_unknown_node_404(client):
    c, _ = client
    assert c.post("/api/node/9999/dismiss").status_code == 404


def test_dismiss_source_node_400(client):
    c, _ = client
    sid = _ingest(c, note="Graphs model relationships.")["source_id"]
    assert c.post(f"/api/node/{sid}/dismiss").status_code == 400
