from alexandria_core.providers.base import Vector

_TASK = "Given a search query, retrieve relevant passages from the knowledge graph"


def format_for_kind(text: str, *, kind: str) -> str:
    if kind == "query":
        return f"Instruct: {_TASK}\nQuery: {text}"
    return text


class Qwen3Embedder:
    """Local Qwen3-Embedding-0.6B via sentence-transformers. Model is fixed (not pluggable)."""

    def __init__(self, model_name: str, dim: int = 1024):
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: list[str], *, kind: str) -> list[Vector]:
        self._ensure()
        prepared = [format_for_kind(t, kind=kind) for t in texts]
        vecs = self._model.encode(prepared, normalize_embeddings=True)
        return [v[: self.dim].tolist() for v in vecs]  # MRL truncation to fixed dim
