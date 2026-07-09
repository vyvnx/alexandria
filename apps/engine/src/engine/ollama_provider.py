import json

from pydantic import ValidationError

from alexandria_core.providers.base import Extraction, ExtractedNode, Relation, TopicMatch
from alexandria_core.graph.models import TYPED_EDGES
from .openai_provider import (_ExtractionModel, _RelationsModel, _TopicModel,
                              extract_sys, _RELATE_SYS, _TOPIC_SYS)


class OllamaProvider:
    def __init__(self, host: str, model: str):
        import ollama
        self.client = ollama.Client(host=host)
        self.model = model

    def _chat_json(self, system: str, user: str) -> dict:
        resp = self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            format="json",
            options={"temperature": 0},
        )
        return json.loads(resp["message"]["content"])

    def summarize(self, text: str) -> str:
        resp = self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": "Summarize in 2-3 sentences."},
                      {"role": "user", "content": text}],
            options={"temperature": 0},
        )
        return resp["message"]["content"].strip()

    def extract(self, text: str, *, abstraction: str = "balanced") -> Extraction:
        try:
            m = _ExtractionModel.model_validate(self._chat_json(extract_sys(abstraction), text))
        except (ValidationError, json.JSONDecodeError, KeyError):
            return Extraction()
        ents = [ExtractedNode(e.name, "entity", e.description, e.type) for e in m.entities]
        cons = [ExtractedNode(c.name, "concept", c.description, None) for c in m.concepts]
        return Extraction(entities=ents, concepts=cons)

    def relate(self, names: list[str], text: str) -> list[Relation]:
        prompt = f"NAMES: {names}\n\nTEXT:\n{text}"
        try:
            m = _RelationsModel.model_validate(self._chat_json(_RELATE_SYS, prompt))
        except (ValidationError, json.JSONDecodeError, KeyError):
            return []
        allowed = set(names)
        return [Relation(r.src_name, r.dst_name, r.type, r.evidence) for r in m.relations
                if r.src_name in allowed and r.dst_name in allowed and r.type in TYPED_EDGES]

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        prompt = f'Label A: "{label_a}"\nLabel B: "{label_b}"'
        try:
            m = _TopicModel.model_validate(self._chat_json(_TOPIC_SYS, prompt))
        except (ValidationError, json.JSONDecodeError, KeyError):
            return TopicMatch(same_topic=False, reason="parse-error")
        return TopicMatch(m.same_topic, m.canonical_topic, m.reason)

    def describe_image(self, images: list[bytes], prompt: str) -> str:
        resp = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt, "images": list(images)}],
            options={"temperature": 0},
        )
        return resp["message"]["content"].strip()
