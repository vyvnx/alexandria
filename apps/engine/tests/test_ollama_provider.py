from alexandria_engine.ollama_provider import OllamaProvider
from alexandria_core.providers.base import Extraction, TopicMatch


def test_extract_parses(monkeypatch):
    payload = {"entities": [{"name": "Ollama", "type": "tool", "description": "runner"}],
               "concepts": [{"name": "inference", "description": "running models"}]}
    p = OllamaProvider(host="http://x", model="llama3.1")
    monkeypatch.setattr(p, "_chat_json", lambda sys, usr: payload)
    e = p.extract("text")
    assert isinstance(e, Extraction)
    assert e.entities[0].name == "Ollama" and e.concepts[0].name == "inference"


def test_relate_filters(monkeypatch):
    payload = {"relations": [{"src_name": "A", "dst_name": "B", "type": "uses", "evidence": "e"}]}
    p = OllamaProvider(host="http://x", model="llama3.1")
    monkeypatch.setattr(p, "_chat_json", lambda sys, usr: payload)
    rels = p.relate(["A", "B"], "text")
    assert len(rels) == 1 and rels[0].type == "uses"


def test_same_topic_parses(monkeypatch):
    p = OllamaProvider(host="http://x", model="llama3.1")
    monkeypatch.setattr(p, "_chat_json", lambda system, user: {
        "same_topic": False, "canonical_topic": None, "reason": "different concepts"})
    m = p.same_topic("Java", "JavaScript")
    assert isinstance(m, TopicMatch) and m.same_topic is False
