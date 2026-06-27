from alexandria_core.config import Settings


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
    monkeypatch.setenv("ALEX_LLM", "ollama")
    monkeypatch.setenv("ALEX_SIMILAR_TOP_K", "9")
    s = Settings(_env_file=None)
    assert s.llm == "ollama"
    assert s.similar_top_k == 9


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
