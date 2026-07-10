from pathlib import Path

from alexandria_core.config import Settings


def test_relative_db_path_resolves_to_repo_root_absolute(monkeypatch, tmp_path):
    # The bug this guards: sqlite resolves a relative db_path against the process
    # CWD, so the same setting points at different files depending on where the
    # app is launched (apps/http vs repo root) — silently splitting the graph
    # across two .db files. Anchoring to the repo root makes it absolute and
    # CWD-independent.
    monkeypatch.chdir(tmp_path)  # launch from anywhere
    s = Settings(_env_file=None, db_path="../data/alexandria.db")
    assert Path(s.db_path).is_absolute()
    assert s.db_path.endswith("/data/alexandria.db")


def test_absolute_db_path_is_left_alone():
    s = Settings(_env_file=None, db_path="/srv/alexandria.db")
    assert s.db_path == "/srv/alexandria.db"


def test_memory_db_path_is_preserved():
    s = Settings(_env_file=None, db_path=":memory:")
    assert s.db_path == ":memory:"


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm == "openai"
    assert s.embed_dim == 1024
    assert s.similar_top_k == 5
    assert 0.0 <= s.similar_threshold <= 1.0
    # resolution dedup thresholds — decoupled from similar_threshold
    assert s.ambiguous_threshold < s.merge_threshold
    assert 0 < s.fuzzy_ratio <= 100


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALEX_LLM", "fake")
    monkeypatch.setenv("ALEX_SIMILAR_TOP_K", "9")
    s = Settings(_env_file=None)
    assert s.llm == "fake"
    assert s.similar_top_k == 9


def test_openai_base_url_defaults_empty_and_is_overridable(monkeypatch):
    assert Settings(_env_file=None).openai_base_url == ""
    monkeypatch.setenv("ALEX_OPENAI_BASE_URL", "http://localhost:8080/v1")
    s = Settings(_env_file=None)
    assert s.openai_base_url == "http://localhost:8080/v1"


def test_extraction_abstraction_defaults_to_balanced():
    s = Settings(_env_file=None)
    assert s.extraction_abstraction == "balanced"
    # abstract pulls fewer entities than balanced
    assert s.extract_entity_cap_abstract < s.extract_entity_cap_balanced


def test_entity_cap_per_level():
    s = Settings(_env_file=None)
    assert s.entity_cap("abstract") == s.extract_entity_cap_abstract
    assert s.entity_cap("balanced") == s.extract_entity_cap_balanced
    assert s.entity_cap("exhaustive") is None  # unlimited


def test_entity_cap_none_uses_the_configured_default_level():
    s = Settings(_env_file=None, extraction_abstraction="abstract")
    assert s.entity_cap(None) == s.extract_entity_cap_abstract


def test_entity_cap_unknown_level_falls_back_to_default_level():
    s = Settings(_env_file=None)  # default balanced
    assert s.entity_cap("nonsense") == s.extract_entity_cap_balanced


def test_visual_enrichment_defaults():
    s = Settings(_env_file=None)
    assert s.openai_vision_model == "gpt-4o-mini"
    assert s.screenshot_viewport_width == 1280
    assert s.screenshot_timeout_ms == 15000
    assert s.screenshot_max_segments == 4


def test_visual_env_override(monkeypatch):
    monkeypatch.setenv("ALEX_OPENAI_VISION_MODEL", "gpt-4o")
    monkeypatch.setenv("ALEX_SCREENSHOT_MAX_SEGMENTS", "2")
    s = Settings(_env_file=None)
    assert s.openai_vision_model == "gpt-4o"
    assert s.screenshot_max_segments == 2
