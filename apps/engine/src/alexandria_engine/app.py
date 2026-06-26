"""Engine-as-a-service: exposes the GPU/ML providers over HTTP.

In v1 the API imports the engine in-process (via `factory`). This thin service is
the seam for later running the engine as its own container — e.g. on a GPU box —
so `apps/api` can call `/embed` over the network instead of loading torch itself.
"""
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from alexandria_core.config import get_settings, Settings
from . import factory


class EmbedBody(BaseModel):
    texts: list[str]
    kind: Literal["query", "document"] = "document"


class SummarizeBody(BaseModel):
    text: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    embedder = factory.build_embedder(settings)
    llm = factory.build_llm(settings)

    app = FastAPI(title="Alexandria Engine")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "llm": settings.llm, "embed_model": settings.embed_model,
                "embed_dim": settings.embed_dim}

    @app.post("/embed")
    def embed(body: EmbedBody):
        vectors = embedder.embed(body.texts, kind=body.kind)
        return {"dim": settings.embed_dim, "vectors": vectors}

    @app.post("/summarize")
    def summarize(body: SummarizeBody):
        return {"summary": llm.summarize(body.text)}

    return app
