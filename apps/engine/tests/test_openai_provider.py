import json

from alexandria_engine.openai_provider import OpenAIProvider
from alexandria_core.providers.base import Extraction, TopicMatch


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class _FakeClient:
    def __init__(self, content):
        self._content = content

    @property
    def chat(self):
        client = self

        class _Comp:
            def create(self, **kw):
                return _FakeResp(client._content)

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
