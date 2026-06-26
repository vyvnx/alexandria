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
