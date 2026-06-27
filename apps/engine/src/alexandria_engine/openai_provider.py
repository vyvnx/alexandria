import json

from pydantic import BaseModel, ValidationError

from alexandria_core.providers.base import Extraction, ExtractedNode, Relation, TopicMatch
from alexandria_core.graph.models import TYPED_EDGES


class _Ent(BaseModel):
    name: str
    type: str | None = None
    description: str = ""


class _TopicModel(BaseModel):
    same_topic: bool
    canonical_topic: str | None = None
    reason: str = ""


class _ExtractionModel(BaseModel):
    entities: list[_Ent] = []
    concepts: list[_Ent] = []


class _Rel(BaseModel):
    src_name: str
    dst_name: str
    type: str
    evidence: str = ""


class _RelationsModel(BaseModel):
    relations: list[_Rel] = []


_EXTRACT_JSON = (
    'Return JSON {"entities":[{"name","type","description"}],'
    '"concepts":[{"name","description"}]}. Keep names canonical and short.'
)
# How selective the extractor is, by abstraction level. Concepts stay broad at
# every level; the levels differ in how aggressively they prune entities.
_EXTRACT_SELECTIVITY = {
    "abstract": (
        "Extract ONLY the handful of entities (people, orgs, tools, papers) truly central "
        "to the text — its main subjects. Skip incidental mentions, members of lists or tables, "
        "and names that merely appear in passing. Still extract the key abstract concepts. "
    ),
    "balanced": (
        "Extract the notable named entities (people, orgs, tools, papers) and the abstract "
        "concepts from the text. Skip trivia and names that only appear in passing. "
    ),
    "exhaustive": (
        "Extract named entities (people, orgs, tools, papers) and abstract concepts from the text. "
    ),
}


def extract_sys(abstraction: str) -> str:
    """System prompt for the extractor at a given abstraction level."""
    lead = _EXTRACT_SELECTIVITY.get(abstraction, _EXTRACT_SELECTIVITY["balanced"])
    return lead + _EXTRACT_JSON
_RELATE_SYS = (
    "Given a list of node names and the source text, return typed relations among them as JSON "
    '{"relations":[{"src_name","dst_name","type","evidence"}]}. '
    "type in {uses, extends, contradicts, about, authored-by}. Only use the provided names. "
    "evidence is a short quote/reason."
)
_TOPIC_SYS = (
    "You are a strict topic deduplication classifier. "
    "Decide whether two labels refer to the same topic. Return only valid JSON.\n"
    "Rules:\n"
    "- Same topic if they are aliases, numbering variants, spelling variants, or minor "
    "wording changes.\n"
    "- Different topic if one is broader, narrower, prerequisite, implementation, example, "
    "or related but not equivalent.\n"
    "- Ignore numbers like 1, 2, part 1, part 2, version labels unless they indicate "
    "different concepts.\n"
    'Return: {"same_topic": boolean, "canonical_topic": string | null, "reason": string}'
)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _chat_json(self, system: str, user: str) -> dict:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)

    def summarize(self, text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "Summarize in 2-3 sentences."},
                      {"role": "user", "content": text}],
            temperature=0,
        )
        return resp.choices[0].message.content.strip()

    def extract(self, text: str, *, abstraction: str = "balanced") -> Extraction:
        try:
            m = _ExtractionModel.model_validate(self._chat_json(extract_sys(abstraction), text))
        except (ValidationError, json.JSONDecodeError):
            return Extraction()
        ents = [ExtractedNode(e.name, "entity", e.description, e.type) for e in m.entities]
        cons = [ExtractedNode(c.name, "concept", c.description, None) for c in m.concepts]
        return Extraction(entities=ents, concepts=cons)

    def relate(self, names: list[str], text: str) -> list[Relation]:
        prompt = f"NAMES: {names}\n\nTEXT:\n{text}"
        try:
            m = _RelationsModel.model_validate(self._chat_json(_RELATE_SYS, prompt))
        except (ValidationError, json.JSONDecodeError):
            return []
        allowed = set(names)
        return [Relation(r.src_name, r.dst_name, r.type, r.evidence) for r in m.relations
                if r.src_name in allowed and r.dst_name in allowed and r.type in TYPED_EDGES]

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        prompt = f'Label A: "{label_a}"\nLabel B: "{label_b}"'
        try:
            m = _TopicModel.model_validate(self._chat_json(_TOPIC_SYS, prompt))
        except (ValidationError, json.JSONDecodeError):
            return TopicMatch(same_topic=False, reason="parse-error")
        return TopicMatch(m.same_topic, m.canonical_topic, m.reason)
