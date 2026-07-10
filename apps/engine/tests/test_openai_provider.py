import json

import pytest

from engine.openai_provider import OpenAIProvider, extract_sys, parse_json_lenient
from alexandria_core.providers.base import Extraction, TopicMatch


class _FakeResp:
    def __init__(self, content, usage=None):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]
        if usage is not None:
            self.usage = usage


class _FakeClient:
    def __init__(self, content, usage=None):
        self._content = content
        self._usage = usage

    @property
    def chat(self):
        client = self

        class _Comp:
            def create(self, **kw):
                return _FakeResp(client._content, client._usage)

        return type("Chat", (), {"completions": _Comp()})()


def test_extract_parses_structured_json():
    payload = json.dumps({
        "entities": [{"name": "Vaswani", "type": "person", "description": "author"}],
        "concepts": [{"name": "attention", "description": "mechanism"}],
    })
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    p.client = _FakeClient(payload)
    e = p.extract("text")
    assert isinstance(e, Extraction)
    assert e.entities[0].name == "Vaswani" and e.entities[0].type == "person"
    assert e.concepts[0].name == "attention"


def test_extract_sys_varies_by_abstraction_level():
    abstract = extract_sys("abstract")
    balanced = extract_sys("balanced")
    exhaustive = extract_sys("exhaustive")
    assert len({abstract, balanced, exhaustive}) == 3
    # abstract steers the model toward only the most central entities
    assert "central" in abstract.lower() or "only" in abstract.lower()


def test_extract_unknown_level_falls_back_to_balanced():
    assert extract_sys("nonsense") == extract_sys("balanced")


def test_extract_uses_the_prompt_for_the_requested_level(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    seen = {}

    def _capture(system, user):
        seen["system"] = system
        return {"entities": [], "concepts": []}

    monkeypatch.setattr(p, "_chat_json", _capture)
    p.extract("text", abstraction="abstract")
    assert seen["system"] == extract_sys("abstract")


def test_relate_parses_and_filters_unknown_names():
    payload = json.dumps({"relations": [
        {"src_name": "A", "dst_name": "B", "type": "extends", "evidence": "x"},
        {"src_name": "A", "dst_name": "Z", "type": "uses", "evidence": "bad"},  # Z unknown → dropped
    ]})
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    p.client = _FakeClient(payload)
    rels = p.relate(["A", "B"], "text")
    assert len(rels) == 1 and rels[0].type == "extends"


def test_same_topic_parses(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    monkeypatch.setattr(p, "_chat_json", lambda system, user: {
        "same_topic": True, "canonical_topic": "Dijkstra's algorithm", "reason": "aliases"})
    m = p.same_topic("Dijkstra algorithm 1", "Dijkstra algorithm 2")
    assert isinstance(m, TopicMatch)
    assert m.same_topic is True and m.canonical_topic == "Dijkstra's algorithm"


def test_same_topic_defaults_false_on_bad_json(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    monkeypatch.setattr(p, "_chat_json", lambda system, user: {"unexpected": 1})
    assert p.same_topic("A", "B").same_topic is False


def test_extract_sys_frames_knowledge_map_at_every_level():
    for level in ("abstract", "balanced", "exhaustive"):
        s = extract_sys(level)
        assert "personal knowledge map" in s
        assert "NEVER extract" in s
        # json contract still present
        assert '"concepts"' in s


def test_extract_sys_injects_interest_context():
    s = extract_sys("balanced", interests=["cloud architecture", "Victorian era"],
                    avoid=["Patreon", "exam scoring"])
    assert "cloud architecture" in s and "Victorian era" in s
    assert "Patreon" in s and "exam scoring" in s
    # empty context leaves the prompt exactly as before
    assert extract_sys("balanced", interests=(), avoid=()) == extract_sys("balanced")
    assert "Patreon" not in extract_sys("balanced")


def test_extract_passes_interest_context_through(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    seen = {}

    def _capture(system, user):
        seen["system"] = system
        return {"entities": [], "concepts": []}

    monkeypatch.setattr(p, "_chat_json", _capture)
    p.extract("text", abstraction="abstract", interests=["aws"], avoid=["Patreon"])
    assert seen["system"] == extract_sys("abstract", interests=["aws"], avoid=["Patreon"])


def test_parse_json_lenient_handles_fences_and_prose():
    assert parse_json_lenient('{"a": 1}') == {"a": 1}
    assert parse_json_lenient('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_lenient('Sure! Here it is:\n{"a": 1}\nHope that helps.') == {"a": 1}
    # braces inside strings don't confuse the fallback scan
    assert parse_json_lenient('noise {"a": "{b}"} noise') == {"a": "{b}"}
    with pytest.raises(json.JSONDecodeError):
        parse_json_lenient("no json here at all")


def test_extract_retries_once_with_repair_note(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    calls = []

    def _flaky(system, user):
        calls.append(user)
        if len(calls) == 1:
            raise json.JSONDecodeError("garbage", "x", 0)
        return {"entities": [], "concepts": [{"name": "attention", "description": ""}]}

    monkeypatch.setattr(p, "_chat_json", _flaky)
    e = p.extract("text")
    assert e.concepts[0].name == "attention"
    assert len(calls) == 2 and "not valid JSON" in calls[1]


def test_extract_returns_empty_after_two_failures(monkeypatch):
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    monkeypatch.setattr(p, "_chat_json", lambda s, u: {"entities": "not-a-list"})
    e = p.extract("text")
    assert e.entities == [] and e.concepts == []


def test_extract_parses_fenced_json_end_to_end():
    # a small model wrapping valid JSON in a code fence still extracts
    payload = "```json\n" + json.dumps({
        "entities": [{"name": "Vaswani", "type": "person", "description": "author"}],
        "concepts": [],
    }) + "\n```"
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    p.client = _FakeClient(payload)
    assert p.extract("text").entities[0].name == "Vaswani"


def test_usage_reported_to_telemetry():
    from alexandria_core.telemetry import MeteredLLM, TelemetryStore
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})
    p.client = _FakeClient("a summary", usage=usage)
    store = TelemetryStore(":memory:")
    assert MeteredLLM(p, store).summarize("text") == "a summary"
    row = store.conn.execute("SELECT * FROM llm_call").fetchone()
    assert (row["prompt_tokens"], row["completion_tokens"]) == (7, 3)
    assert row["model"] == "gpt-4o-mini"


def test_missing_usage_degrades_to_tokenless_record():
    from alexandria_core.telemetry import MeteredLLM, TelemetryStore
    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    p.client = _FakeClient("a summary")  # no usage on the response
    store = TelemetryStore(":memory:")
    assert MeteredLLM(p, store).summarize("text") == "a summary"
    row = store.conn.execute("SELECT prompt_tokens FROM llm_call").fetchone()
    assert row["prompt_tokens"] is None


def test_base_url_reaches_openai_client():
    p = OpenAIProvider(api_key="sk", model="qwen2.5:7b", base_url="http://localhost:8080/v1")
    assert str(p.client.base_url).startswith("http://localhost:8080/v1")
