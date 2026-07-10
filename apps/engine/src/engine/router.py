"""Per-task model routing (small-model roadmap item B, roadmap A4/F4).

llama.cpp serves one model per process, so the routing key is a base URL:
easy jobs (summarize, same_topic) can hit a small local server while the
hard jobs (extract, relate) keep the strong model. Over budget, everything
flips to the fallback (local) provider instead of deferring the queue.
Routing is invisible above the provider seam.
"""
from collections.abc import Callable

from alexandria_core.providers.base import Extraction, LLMProvider, Relation, TopicMatch


class RoutedLLM:
    def __init__(self, default: LLMProvider,
                 by_task: dict[str, LLMProvider] | None = None,
                 fallback: LLMProvider | None = None,
                 over_budget: Callable[[], bool] | None = None):
        self.default = default
        self.by_task = by_task or {}
        self.fallback = fallback
        self.over_budget = over_budget or (lambda: False)

    @property
    def model(self) -> str:
        # display only — telemetry records each call's actual model via add_usage
        return getattr(self.default, "model", "")

    def _pick(self, task: str) -> LLMProvider:
        if self.fallback is not None and self.over_budget():
            return self.fallback
        return self.by_task.get(task, self.default)

    def summarize(self, text: str) -> str:
        return self._pick("summarize").summarize(text)

    def extract(self, text: str, **kw) -> Extraction:
        return self._pick("extract").extract(text, **kw)

    def relate(self, names: list[str], text: str) -> list[Relation]:
        return self._pick("relate").relate(names, text)

    def same_topic(self, label_a: str, label_b: str) -> TopicMatch:
        return self._pick("same_topic").same_topic(label_a, label_b)

    def answer(self, question: str, context: str) -> str:
        return self._pick("answer").answer(question, context)
