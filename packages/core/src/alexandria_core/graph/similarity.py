from .store import GraphStore


def top_k_similar(store: GraphStore, node_id: int, vector: list[float],
                  k: int, threshold: float) -> list[tuple[int, float]]:
    """Nearest neighbours of `vector`, excluding `node_id`, above `threshold`, capped at k."""
    hits = store.knn(vector, k + 1)  # +1 because self is usually the top hit
    out = [(nid, score) for nid, score in hits if nid != node_id and score >= threshold]
    return out[:k]
