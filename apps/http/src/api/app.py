import sqlite3
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alexandria_core.config import get_settings, Settings
from alexandria_core.graph.models import KIND_SOURCE
from alexandria_core.graph.store import GraphStore
from alexandria_core.ingest.pipeline import ingest
from alexandria_core.ask import ask as graphrag_ask
from alexandria_core.insights import compute_insights
from alexandria_core.intake import IntakeRegistry, poll_feeds
from alexandria_core.logging_config import configure_logging, get_logger
from alexandria_core.telemetry import (
    MeteredEmbedder, MeteredLLM, MeteredVision, TelemetryStore, set_current_execution,
)
from engine import factory

log = get_logger("api")


class FeedBody(BaseModel):
    url: str
    cadence_minutes: int = 60


class TopicBody(BaseModel):
    name: str
    weight: float = 1.0


class IngestBody(BaseModel):
    url: str | None = None
    note: str | None = None
    # How much to pull from this source. None ⇒ the server's default level.
    abstraction: Literal["abstract", "balanced", "exhaustive"] | None = None
    # opt-in: screenshot the page and let a VLM read tables/charts (needs a url)
    visual: bool = False


def create_app(store=None, llm=None, embedder=None, settings: Settings | None = None,
               vision=None, registry=None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    if store is None:
        store = GraphStore(settings.db_path)
        store.init_schema()
    # curated feed/topic registry (A3) — domain data, lives in the graph db file
    registry = registry or IntakeRegistry(settings.db_path)
    # every provider (injected fakes included) is metered through the telemetry
    # seam (F1): per-call task/tokens/cost/duration, grouped by ingest execution
    telemetry = TelemetryStore(settings.executions_db_path,
                               price_in_per_mtok=settings.price_in_per_mtok,
                               price_out_per_mtok=settings.price_out_per_mtok)

    # budgets (roadmap F3): metered spend against daily/monthly ceilings
    def _window_start(kind: str) -> str:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if kind == "monthly":
            start = start.replace(day=1)
        return start.isoformat()

    def _over_budget() -> str | None:
        if (settings.budget_daily_usd
                and telemetry.spend_since(_window_start("daily")) >= settings.budget_daily_usd):
            return "daily"
        if (settings.budget_monthly_usd
                and telemetry.spend_since(_window_start("monthly")) >= settings.budget_monthly_usd):
            return "monthly"
        return None

    llm = MeteredLLM(llm or factory.build_llm(
        settings, over_budget=lambda: _over_budget() is not None), telemetry)
    embedder = MeteredEmbedder(embedder or factory.build_embedder(settings), telemetry)
    vision = MeteredVision(vision or factory.build_vision(settings), telemetry)

    log.info("Alexandria API ready — db=%s llm=%s vec=%s",
             settings.db_path, settings.llm, store.vec_available)
    if not store.vec_available:
        log.warning("sqlite-vec unavailable — /search falls back to name matching")

    # persistent ingest queue (roadmap A1): the execution row IS the job —
    # POST /ingest enqueues it, the worker below claims and runs it, and the
    # same row is what GET /executions lists. Queued jobs survive a restart.
    # ponytail: one worker thread, one uvicorn process; add workers when
    # ingest volume demands it
    wake = threading.Event()
    stop = threading.Event()

    def _run_job(row: dict):
        eid = row["id"]
        body = IngestBody(**(row["payload"] or {}))
        set_current_execution(eid)
        try:
            res = ingest(store, llm, embedder, settings, url=body.url, note=body.note,
                         abstraction=body.abstraction, visual=body.visual, vision=vision,
                         on_stage=lambda s: telemetry.set_stage(eid, s))
            telemetry.finish_execution(eid, "succeeded", result=asdict(res))
        except Exception:
            log.exception("ingest failed for source=%s", row["source"])
            telemetry.finish_execution(eid, "failed", error="ingest failed — see server logs")
        finally:
            set_current_execution(None)

    budget_paused = False

    def _worker():
        nonlocal budget_paused
        while not stop.is_set():
            # ponytail: hard stop = defer everything until the window resets;
            # salience-aware partial deferral is F4+ territory. with a local
            # fallback configured, RoutedLLM flips there instead — keep running.
            over = _over_budget() if not settings.fallback_base_url else None
            if over is not None:
                if not budget_paused:
                    log.warning("llm budget (%s) reached — deferring queued ingests", over)
                    budget_paused = True
                wake.wait(timeout=0.5)
                wake.clear()
                continue
            budget_paused = False
            row = telemetry.claim_next()
            if row is not None:
                _run_job(row)
                continue
            # idle: poll due feeds (A3) — discovered items enter the same queue
            try:
                poll_feeds(registry, store, embedder, telemetry, settings)
            except Exception:
                log.exception("feed polling failed")
            wake.wait(timeout=0.5)
            wake.clear()

    @asynccontextmanager
    async def lifespan(_app):
        interrupted = telemetry.recover()
        if interrupted:
            log.warning("failed %d ingest job(s) interrupted by restart", interrupted)
        threading.Thread(target=_worker, name="ingest-worker", daemon=True).start()
        yield
        stop.set()
        wake.set()

    app = FastAPI(title="Alexandria", lifespan=lifespan)
    app.state.store, app.state.llm, app.state.embedder, app.state.settings = (
        store, llm, embedder, settings)
    app.state.vision = vision
    app.state.telemetry = telemetry
    app.state.registry = registry

    def _node_dict(n):
        return {"id": n.id, "kind": n.kind, "name": n.name, "data": n.data}

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "vec": store.vec_available, "llm": settings.llm}

    @app.get("/config")
    def config():
        # The client-facing "where viz config lives" seam — a dedicated endpoint
        # (health stays health). The browser reads these on load to size stars
        # and cluster galaxies; changing a knob is an .env edit + restart.
        s = app.state.settings
        return {
            "star_size_min": s.star_size_min,
            "star_size_max": s.star_size_max,
            "galaxy_resolution": s.galaxy_resolution,
            "min_galaxy_size": s.min_galaxy_size,
            "extraction_abstraction": s.extraction_abstraction,
        }

    @app.post("/ingest")
    def do_ingest(body: IngestBody):
        if not body.url and not body.note:
            raise HTTPException(400, "provide url and/or note")
        job_id = telemetry.enqueue(body.url or "note", body.model_dump())
        wake.set()
        return {"job_id": str(job_id)}

    # frozen polling contract for the web ChartProgress: status running|done|failed
    _JOB_STATUS = {"queued": "running", "running": "running",
                   "succeeded": "done", "failed": "failed"}

    @app.get("/ingest/{job_id}")
    def ingest_status(job_id: str):
        row = telemetry.get_execution(int(job_id)) if job_id.isdigit() else None
        if row is None:
            raise HTTPException(404, "unknown job")
        return {"status": _JOB_STATUS[row["status"]], "stage": row["stage"],
                "result": row["result"], "error": row["error"]}

    @app.get("/executions")
    def executions(limit: int = 50):
        # cost/status ledger for the /executions panel (F1)
        return telemetry.list_executions(limit)

    @app.get("/insights")
    def insights():
        # structural insights over the graph tier (D2), computed on demand
        return compute_insights(store, settings)

    @app.get("/ask")
    def ask_endpoint(q: str = ""):
        # graphrag q&a (D3): cited answer from a connected subgraph
        if not q.strip():
            raise HTTPException(400, "provide a question via ?q=")
        return graphrag_ask(store, embedder, llm, settings, q)

    @app.get("/usage")
    def usage(days: int = 30):
        # where the money goes (F2): totals + per-day/task/source rollups
        u = telemetry.usage(days)
        u["budget"] = {
            "daily_usd": settings.budget_daily_usd,
            "monthly_usd": settings.budget_monthly_usd,
            "spent_today_usd": telemetry.spend_since(_window_start("daily")),
            "spent_month_usd": telemetry.spend_since(_window_start("monthly")),
            "over": _over_budget(),
        }
        return u

    @app.get("/feeds")
    def list_feeds():
        return registry.list_feeds()

    @app.post("/feeds")
    def add_feed(body: FeedBody):
        try:
            fid = registry.add_feed(body.url, cadence_minutes=body.cadence_minutes)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "feed already registered")
        return {"id": fid}

    @app.delete("/feeds/{feed_id}")
    def remove_feed(feed_id: int):
        if not registry.feed_exists(feed_id):
            raise HTTPException(404, "unknown feed")
        registry.remove_feed(feed_id)
        return {"removed": feed_id}

    @app.post("/feeds/{feed_id}/poll")
    def poll_feed(feed_id: int):
        if not registry.feed_exists(feed_id):
            raise HTTPException(404, "unknown feed")
        registry.poll_now(feed_id)
        wake.set()
        return {"polling": feed_id}

    @app.get("/topics")
    def list_topics():
        return registry.list_topics()

    @app.post("/topics")
    def add_topic(body: TopicBody):
        try:
            tid = registry.add_topic(body.name, weight=body.weight)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "topic already exists")
        return {"id": tid}

    @app.delete("/topics/{topic_id}")
    def remove_topic(topic_id: int):
        if not registry.topic_exists(topic_id):
            raise HTTPException(404, "unknown topic")
        registry.remove_topic(topic_id)
        return {"removed": topic_id}

    @app.get("/graph")
    def graph(node_id: int | None = None, k: int = 2):
        if node_id is not None:
            ids = set(store.reach(node_id, k))
            nodes = [n for n in store.all_nodes() if n.id in ids]
            edges = [e for e in store.all_edges() if e.src_id in ids and e.dst_id in ids]
        else:
            nodes = store.all_nodes()
            edges = store.all_edges()
        return {
            # trimmed wire shape (roadmap B1): no data blob — the dossier
            # lazy-loads it via /node/{id}
            "nodes": [{"id": n.id, "kind": n.kind, "name": n.name} for n in nodes],
            "edges": [{"src": e.src_id, "dst": e.dst_id, "type": e.type, "weight": e.weight}
                      for e in edges],
        }

    @app.get("/search")
    def search(q: str):
        results = []
        if store.vec_available:
            qvec = embedder.embed([q], kind="query")[0]
            for nid, score in store.knn(qvec, 20):
                n = store.get_node(nid)
                if n:
                    results.append({"id": n.id, "kind": n.kind, "name": n.name,
                                    "score": round(score, 4)})
        if not results:  # fallback: name LIKE
            needle = q.lower()
            for n in store.all_nodes():
                if needle in n.name.lower():
                    results.append({"id": n.id, "kind": n.kind, "name": n.name, "score": None})
        log.info("search %r -> %d results (%s)", q, len(results),
                 "vector" if store.vec_available else "name-match")
        return results

    @app.get("/node/{node_id}")
    def node_detail(node_id: int):
        n = store.get_node(node_id)
        if not n:
            raise HTTPException(404, "node not found")
        neighbors = []
        for e in store.edges_for(node_id):
            other = store.get_node(e.dst_id if e.src_id == node_id else e.src_id)
            if other:
                neighbors.append({"node": _node_dict(other),
                                  "edge": {"type": e.type, "weight": e.weight,
                                           "evidence": e.evidence}})
        return {"node": _node_dict(n), "source": store.get_source(node_id),
                "neighbors": neighbors}

    @app.post("/node/{node_id}/dismiss")
    def dismiss_node(node_id: int):
        n = store.get_node(node_id)
        if not n:
            raise HTTPException(404, "node not found")
        if n.kind == KIND_SOURCE:
            raise HTTPException(400, "source nodes cannot be dismissed")
        name = store.dismiss_node(node_id)
        log.info("dismissed node %d %r — topic suppressed in future ingests", node_id, name)
        return {"dismissed": name}

    # serve the built SPA if present (apps/web/dist) — mounted last so API routes win.
    # The frontend is built later; until then this mount is simply skipped.
    dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
