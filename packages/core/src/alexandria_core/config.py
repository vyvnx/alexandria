from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, resolved from this file so it loads regardless of the process
# CWD. Each app's `dev`/`test` script runs from its own folder (apps/api, ...),
# so a relative env_file=".env" would silently miss the root .env.
# config.py -> alexandria_core -> src -> core -> packages -> repo root
_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALEX_", env_file=_ENV_FILE, extra="ignore"
    )

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
