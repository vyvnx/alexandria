import base64
import json
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from alexandria_core.logging_config import get_logger
from alexandria_core.providers.base import Extraction, ExtractedNode, Relation, TopicMatch
from alexandria_core.graph.models import TYPED_EDGES
from alexandria_core.telemetry import add_usage

log = get_logger("llm")


def parse_json_lenient(raw: str) -> dict:
    """Parse model output as JSON, tolerating the ways small models wrap it:
    markdown code fences, surrounding prose, trailing text. Falls back to the
    first parseable {...} object anywhere in the string."""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = raw.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(raw, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = raw.find("{", idx + 1)
    raise json.JSONDecodeError("no JSON object in model output", raw, 0)


_REPAIR_NOTE = ("\n\nYour previous reply was not valid JSON for the requested schema. "
                "Reply again with ONLY the JSON object — no prose, no code fences.")


def chat_validated(chat_json, system: str, user: str, model_cls):
    """One JSON chat round-trip validated against a pydantic model, with a single
    repair retry when the output is malformed. Returns None if both attempts
    fail — callers degrade to their empty result, loudly (warning log), never
    silently."""
    msg = user
    for _ in range(2):
        try:
            return model_cls.model_validate(chat_json(system, msg))
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            err = e
            msg = user + _REPAIR_NOTE
    log.warning("%s: model output failed validation after retry: %s",
                model_cls.__name__, err)
    return None


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
# purpose framing shared by every abstraction level: the extraction builds a
# personal knowledge map, so page furniture and source administrivia are
# excluded outright. the levels below only steer entity selectivity.
_EXTRACT_FRAME = (
    "You are building a personal knowledge map of topics the reader is learning about. "
    "Concepts are knowledge topics one can be interested in and explore further — "
    "disciplines, ideas, techniques, technologies, methods, historical periods "
    '(e.g. "cloud solution design", "Victorian era", "spaced repetition"). '
    "Include something only if it would be a meaningful topic on that map.\n"
    "NEVER extract:\n"
    "- website boilerplate: donation or membership platforms, newsletters, "
    "subscription or paywall prompts, social media links, cookie banners, site navigation;\n"
    "- administrivia about the source or its subject's logistics: exam scoring, "
    "registration, fees, pricing, schedules, shipping, terms of service, author bios.\n"
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


def extract_sys(abstraction: str, *, interests: Sequence[str] = (),
                avoid: Sequence[str] = ()) -> str:
    """System prompt for the extractor at a given abstraction level, optionally
    personalized: recurring topics as positive exemplars, dismissals as negative
    few-shots. The prompt tunes itself from the reader's behavior."""
    lead = _EXTRACT_SELECTIVITY.get(abstraction, _EXTRACT_SELECTIVITY["balanced"])
    ctx = ""
    if interests:
        ctx += ("This reader's map already includes: " + ", ".join(interests)
                + ". Reuse these exact names when the text covers the same topic.\n")
    if avoid:
        ctx += ("The reader dismissed these as not interesting — never extract "
                "them or close variants: " + ", ".join(avoid) + ".\n")
    return _EXTRACT_FRAME + ctx + lead + _EXTRACT_JSON
_ANSWER_SYS = (
    "Answer the question using ONLY the numbered context passages. Cite the "
    "passages you use as [n]. If the context is insufficient, say so plainly "
    "instead of guessing. Be concise."
)
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
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        from openai import OpenAI
        # base_url points this provider at any OpenAI-compatible server
        # (llama.cpp, vLLM, LM Studio, OpenRouter, ...); None ⇒ api.openai.com
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def _create(self, **kwargs):
        # single funnel for every chat round-trip so token usage is reported
        # to the telemetry seam (F1) exactly once per api call
        resp = self.client.chat.completions.create(
            model=self.model, temperature=0, **kwargs)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            add_usage(getattr(usage, "prompt_tokens", 0) or 0,
                      getattr(usage, "completion_tokens", 0) or 0, self.model)
        return resp

    def _chat_json(self, system: str, user: str) -> dict:
        resp = self._create(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return parse_json_lenient(resp.choices[0].message.content)

    def summarize(self, text: str) -> str:
        resp = self._create(
            messages=[{"role": "system", "content": "Summarize in 2-3 sentences."},
                      {"role": "user", "content": text}],
        )
        return resp.choices[0].message.content.strip()

    def extract(self, text: str, *, abstraction: str = "balanced",
                interests: Sequence[str] = (), avoid: Sequence[str] = ()) -> Extraction:
        m = chat_validated(self._chat_json,
                           extract_sys(abstraction, interests=interests, avoid=avoid),
                           text, _ExtractionModel)
        if m is None:
            return Extraction()
        ents = [ExtractedNode(e.name, "entity", e.description, e.type) for e in m.entities]
        cons = [ExtractedNode(c.name, "concept", c.description, None) for c in m.concepts]
        return Extraction(entities=ents, concepts=cons)

    def relate(self, names: list[str], text: str) -> list[Relation]:
        prompt = f"NAMES: {names}\n\nTEXT:\n{text}"
        m = chat_validated(self._chat_json, _RELATE_SYS, prompt, _RelationsModel)
        if m is None:
            return []
        allowed = set(names)
        return [Relation(r.src_name, r.dst_name, r.type, r.evidence) for r in m.relations
                if r.src_name in allowed and r.dst_name in allowed and r.type in TYPED_EDGES]

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        prompt = f'Label A: "{label_a}"\nLabel B: "{label_b}"'
        m = chat_validated(self._chat_json, _TOPIC_SYS, prompt, _TopicModel)
        if m is None:
            return TopicMatch(same_topic=False, reason="parse-error")
        return TopicMatch(m.same_topic, m.canonical_topic, m.reason)

    def answer(self, question: str, context: str) -> str:
        resp = self._create(messages=[
            {"role": "system", "content": _ANSWER_SYS},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ])
        return resp.choices[0].message.content.strip()

    def describe_image(self, images: list[bytes], prompt: str) -> str:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"}})
        resp = self._create(messages=[{"role": "user", "content": content}])
        return resp.choices[0].message.content.strip()
