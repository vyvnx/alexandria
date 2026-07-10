from engine.factory import build_llm
from engine.openai_provider import OpenAIProvider
from engine.router import RoutedLLM
from alexandria_core.config import Settings


def _settings(**kw):
    return Settings(_env_file=None, llm="openai", openai_api_key="sk", **kw)


class _Rec:
    """fake provider that records which methods were dispatched to it"""

    def __init__(self, name):
        self.name, self.called = name, []

    def summarize(self, text):
        self.called.append("summarize")
        return self.name

    def extract(self, text, **kw):
        self.called.append("extract")

    def relate(self, names, text):
        self.called.append("relate")

    def same_topic(self, a, b):
        self.called.append("same_topic")


def test_methods_dispatch_to_the_right_provider():
    default, small = _Rec("default"), _Rec("small")
    r = RoutedLLM(default, {"same_topic": small, "summarize": small})
    r.summarize("t")
    r.same_topic("a", "b")
    r.extract("t")
    r.relate(["A"], "t")
    assert small.called == ["summarize", "same_topic"]
    assert default.called == ["extract", "relate"]


def test_no_overrides_returns_the_plain_provider():
    llm = build_llm(_settings())
    assert isinstance(llm, OpenAIProvider)  # byte-identical to the pre-routing path


def test_per_task_override_routes_that_task_only():
    llm = build_llm(_settings(same_topic_base_url="http://localhost:8081/v1"))
    assert isinstance(llm, RoutedLLM)
    assert str(llm._pick("same_topic").client.base_url).startswith("http://localhost:8081/v1")
    assert not str(llm._pick("extract").client.base_url).startswith("http://localhost:8081")


def test_same_url_shares_one_provider_instance():
    llm = build_llm(_settings(summarize_base_url="http://localhost:8081/v1",
                              same_topic_base_url="http://localhost:8081/v1"))
    assert llm._pick("summarize") is llm._pick("same_topic")


def test_over_budget_flips_every_task_to_the_fallback():
    flag = {"over": False}
    llm = build_llm(_settings(fallback_base_url="http://localhost:9090/v1"),
                    over_budget=lambda: flag["over"])
    default = llm._pick("extract")
    flag["over"] = True
    fallback = llm._pick("extract")
    assert fallback is not default
    assert str(fallback.client.base_url).startswith("http://localhost:9090/v1")
    assert llm._pick("summarize") is fallback


def test_over_budget_without_fallback_keeps_normal_routing():
    llm = build_llm(_settings(same_topic_base_url="http://localhost:8081/v1"),
                    over_budget=lambda: True)
    assert str(llm._pick("same_topic").client.base_url).startswith("http://localhost:8081/v1")


def test_routed_llm_exposes_the_default_model():
    llm = build_llm(_settings(fallback_base_url="http://localhost:9090/v1"))
    assert llm.model == "gpt-4o-mini"
