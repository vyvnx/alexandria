from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alexandria_core.config import get_settings, Settings
from alexandria_core.graph.store import GraphStore
from alexandria_core.ingest.pipeline import ingest
from alexandria_core.logging_config import configure_logging, get_logger
from alexandria_engine import factory

log = get_logger("api")


class IngestBody(BaseModel):
    url: str | None = None
    note: str | None = None


def create_app(store=None, llm=None, embedder=None, settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    if store is None:
        store = GraphStore(settings.db_path)
        store.init_schema()
    llm = llm or factory.build_llm(settings)
    embedder = embedder or factory.build_embedder(settings)

    log.info("Alexandria API ready — db=%s llm=%s vec=%s",
             settings.db_path, settings.llm, store.vec_available)
    if not store.vec_available:
        log.warning("sqlite-vec unavailable — /search falls back to name matching")

    app = FastAPI(title="Alexandria")
    app.state.store, app.state.llm, app.state.embedder, app.state.settings = (
        store, llm, embedder, settings)

    def _node_dict(n):
        return {"id": n.id, "kind": n.kind, "name": n.name, "data": n.data}

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "vec": store.vec_available, "llm": settings.llm}

    @app.post("/ingest")
    def do_ingest(body: IngestBody):
        if not body.url and not body.note:
            raise HTTPException(400, "provide url and/or note")
        try:
            res = ingest(store, llm, embedder, settings, url=body.url, note=body.note)
        except Exception:
            log.exception("ingest failed for url=%s", body.url)
            raise HTTPException(500, "ingest failed — see server logs")
        return asdict(res)

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
            "nodes": [_node_dict(n) for n in nodes],
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

    # serve the built SPA if present (apps/web/dist) — mounted last so API routes win.
    # The frontend is built later; until then this mount is simply skipped.
    dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
