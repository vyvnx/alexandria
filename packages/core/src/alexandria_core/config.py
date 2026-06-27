from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALEX_", env_file=".env", extra="ignore")

    llm: Literal["openai", "ollama", "fake"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    db_path: str = "../data/alexandria.db"
    embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embed_dim: int = 1024
    similar_top_k: int = 5
    similar_threshold: float = 0.55       # cosine for similar-to edges (NOT for merging)

    # Entity-resolution / dedup knobs — decoupled from similar_threshold.
    merge_threshold: float = 0.86         # cosine >= this ⇒ same node (auto-merge)
    ambiguous_threshold: float = 0.72     # band [ambiguous, merge) ⇒ ask the LLM
    fuzzy_ratio: int = 90                 # rapidfuzz token_set_ratio cutoff to propose a candidate

    # Extraction abstraction dial — how much each source pulls into the graph.
    # The prompt steers selectivity and a per-source salience cap enforces a
    # hard ceiling on entities (concepts are left uncapped). Set the default
    # here; the web Add panel overrides it per upload. "exhaustive" ⇒ no cap.
    extraction_abstraction: Literal["abstract", "balanced", "exhaustive"] = "balanced"
    extract_entity_cap_abstract: int = 5    # only the few most central entities
    extract_entity_cap_balanced: int = 15   # notable entities, no long tail

    # Visualization knobs — the *computation* (sizing, clustering) runs in the
    # browser; only these tunables live here, env-driven like the LLM provider,
    # and reach the client via GET /config. See the topic-weight-galaxies plan.
    star_size_min: float = 4.0            # smallest star radius
    star_size_max: float = 11.0           # largest star radius (the "not too big" ceiling)
    galaxy_resolution: float = 1.0        # Louvain resolution; higher ⇒ more, smaller galaxies
    min_galaxy_size: int = 3              # communities below this draw no hull (lone stars)


    def entity_cap(self, abstraction: str | None) -> int | None:
        """Per-source entity ceiling for an abstraction level. None ⇒ unlimited.
        Falls back to the configured default for None or an unknown level."""
        level = abstraction if abstraction in _ENTITY_CAPS else self.extraction_abstraction
        cap = _ENTITY_CAPS[level]
        return getattr(self, cap) if cap else None


# level -> the Settings field holding its cap (None ⇒ no cap / unlimited)
_ENTITY_CAPS: dict[str, str | None] = {
    "abstract": "extract_entity_cap_abstract",
    "balanced": "extract_entity_cap_balanced",
    "exhaustive": None,
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
