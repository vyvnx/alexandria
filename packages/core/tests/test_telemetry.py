import pytest

from alexandria_core.providers.fake import FakeLLM, FakeEmbedder, FakeVision
from alexandria_core.telemetry import (
    MeteredEmbedder,
    MeteredLLM,
    MeteredVision,
    TelemetryStore,
    add_usage,
    set_current_execution,
)


@pytest.fixture
def store():
    return TelemetryStore(":memory:")


def _calls(store):
    rows = store.conn.execute("SELECT * FROM llm_call ORDER BY id").fetchall()
    return [dict(r) for r in rows]


class UsageLLM(FakeLLM):
    """fake that reports token usage like a real provider would"""

    model = "test-model"

    def summarize(self, text: str) -> str:
        add_usage(10, 5, self.model)
        return super().summarize(text)

    def extract(self, text: str, **kw):
        # two api round-trips (e.g. a repair retry) accumulate into one call row
        add_usage(100, 20, self.model)
        add_usage(100, 30, self.model)
        return super().extract(text, **kw)


def test_one_row_per_call_with_task_names(store):
    llm = MeteredLLM(FakeLLM(), store)
    llm.summarize("Alpha text")
    llm.extract("Alpha text")
    llm.relate(["A", "B"], "Alpha text")
    llm.same_topic("a", "b")
    MeteredEmbedder(FakeEmbedder(dim=8), store).embed(["x"], kind="query")
    MeteredVision(FakeVision(), store).describe_image([b"png"], "read it")
    assert [c["task"] for c in _calls(store)] == [
        "summarize", "extract", "relate", "same_topic", "embed", "describe_image"]
    assert all(c["duration_ms"] >= 0 for c in _calls(store))


def test_results_pass_through_unchanged(store):
    llm = MeteredLLM(FakeLLM(), store)
    assert llm.summarize("short") == FakeLLM().summarize("short")
    assert llm.same_topic("a", "b").same_topic is False


def test_usage_tokens_accumulate_per_call(store):
    llm = MeteredLLM(UsageLLM(), store)
    llm.summarize("t")
    llm.extract("t")
    summarize, extract = _calls(store)
    assert (summarize["prompt_tokens"], summarize["completion_tokens"]) == (10, 5)
    assert (extract["prompt_tokens"], extract["completion_tokens"]) == (200, 50)
    assert summarize["model"] == "test-model"


def test_missing_usage_degrades_to_tokenless_record(store):
    MeteredLLM(FakeLLM(), store).summarize("t")
    (call,) = _calls(store)
    assert call["prompt_tokens"] is None and call["completion_tokens"] is None
    assert call["cost_usd"] is None


def test_cost_computed_when_priced():
    store = TelemetryStore(":memory:", price_in_per_mtok=1.0, price_out_per_mtok=2.0)
    llm = MeteredLLM(UsageLLM(), store)
    llm.summarize("t")  # 10 in, 5 out
    (call,) = _calls(store)
    assert call["cost_usd"] == pytest.approx(10 / 1e6 * 1.0 + 5 / 1e6 * 2.0)


def test_cost_null_when_unpriced(store):
    MeteredLLM(UsageLLM(), store).summarize("t")
    assert _calls(store)[0]["cost_usd"] is None


def test_add_usage_outside_metered_call_is_noop(store):
    add_usage(5, 5)  # must not raise
    assert _calls(store) == []


def test_execution_groups_calls(store):
    eid = store.enqueue("https://example.com", {})
    store.claim_next()
    set_current_execution(eid)
    MeteredLLM(UsageLLM(), store).summarize("t")
    store.finish_execution(eid, "succeeded", result={"nodes_added": 1})
    (call,) = _calls(store)
    assert call["execution_id"] == eid
    row = store.get_execution(eid)
    assert row["status"] == "succeeded"
    assert row["result"] == {"nodes_added": 1}
    assert row["finished_at"] is not None
    set_current_execution(None)


def test_calls_outside_execution_have_null_execution_id(store):
    MeteredLLM(FakeLLM(), store).summarize("t")
    assert _calls(store)[0]["execution_id"] is None


def test_get_execution_unknown_id(store):
    assert store.get_execution(999) is None


def test_list_executions_newest_first_with_task_breakdown():
    store = TelemetryStore(":memory:", price_in_per_mtok=1.0, price_out_per_mtok=2.0)
    llm = MeteredLLM(UsageLLM(), store)
    e1 = store.enqueue("first", {})
    store.claim_next()
    set_current_execution(e1)
    llm.summarize("t")
    llm.summarize("t")
    store.finish_execution(e1, "succeeded")
    e2 = store.enqueue("second", {})
    store.claim_next()
    set_current_execution(e2)
    llm.extract("t")
    store.finish_execution(e2, "failed", error="boom")
    set_current_execution(None)

    rows = store.list_executions()
    assert [r["id"] for r in rows] == [e2, e1]
    first = rows[1]
    assert first["source"] == "first"
    assert first["prompt_tokens"] == 20 and first["completion_tokens"] == 10
    assert first["tasks"]["summarize"]["calls"] == 2
    assert first["cost_usd"] == pytest.approx(20 / 1e6 * 1.0 + 10 / 1e6 * 2.0)
    assert first["duration_ms"] is not None
    assert rows[0]["status"] == "failed"


def test_stage_updates(store):
    eid = store.enqueue("x", {})
    store.set_stage(eid, "extracting")
    assert store.get_execution(eid)["stage"] == "extracting"


def test_enqueue_then_claim(store):
    eid = store.enqueue("https://x", {"url": "https://x", "visual": False})
    row = store.get_execution(eid)
    assert row["status"] == "queued" and row["started_at"] is None
    claimed = store.claim_next()
    assert claimed["id"] == eid
    assert claimed["payload"] == {"url": "https://x", "visual": False}
    after = store.get_execution(eid)
    assert after["status"] == "running" and after["started_at"] is not None


def test_claim_next_on_empty_queue(store):
    assert store.claim_next() is None


def test_claim_is_fifo(store):
    a = store.enqueue("a", {})
    b = store.enqueue("b", {})
    assert store.claim_next()["id"] == a
    assert store.claim_next()["id"] == b


def test_recover_fails_interrupted_running_but_keeps_queued(store):
    interrupted = store.enqueue("r", {})
    store.claim_next()
    queued = store.enqueue("q", {})
    assert store.recover() == 1
    failed = store.get_execution(interrupted)
    assert failed["status"] == "failed" and "interrupted" in failed["error"]
    assert store.get_execution(queued)["status"] == "queued"


def test_telemetry_failure_never_breaks_the_call(store):
    llm = MeteredLLM(FakeLLM(), store)
    store.conn.close()  # simulate a broken telemetry backend
    assert llm.summarize("still works") == FakeLLM().summarize("still works")


def _seeded_store():
    store = TelemetryStore(":memory:", price_in_per_mtok=1.0, price_out_per_mtok=2.0)
    llm = MeteredLLM(UsageLLM(), store)
    e1 = store.enqueue("https://a.com/x", {})
    store.claim_next()
    set_current_execution(e1)
    llm.summarize("t")   # 10 in, 5 out
    llm.summarize("t")
    store.finish_execution(e1, "succeeded")
    e2 = store.enqueue("https://b.com/y", {})
    store.claim_next()
    set_current_execution(e2)
    llm.extract("t")     # 200 in, 50 out
    store.finish_execution(e2, "succeeded")
    set_current_execution(None)
    return store


def test_usage_rollups():
    store = _seeded_store()
    u = store.usage(days=30)
    assert u["days"] == 30
    assert u["total_calls"] == 3
    assert u["prompt_tokens"] == 220 and u["completion_tokens"] == 60
    assert u["total_cost_usd"] == pytest.approx(220 / 1e6 * 1.0 + 60 / 1e6 * 2.0)
    assert u["per_task"]["summarize"]["calls"] == 2
    assert u["per_task"]["extract"]["prompt_tokens"] == 200
    # all seeded calls happened just now -> one day bucket
    assert len(u["per_day"]) == 1 and u["per_day"][0]["calls"] == 3
    by_source = {r["source"]: r for r in u["per_source"]}
    assert by_source["https://b.com/y"]["cost_usd"] > by_source["https://a.com/x"]["cost_usd"]


def test_usage_window_excludes_old_calls():
    store = _seeded_store()
    store.conn.execute("UPDATE llm_call SET at='2020-01-01T00:00:00+00:00'"
                       " WHERE task='extract'")
    u = store.usage(days=30)
    assert u["total_calls"] == 2 and "extract" not in u["per_task"]


def test_spend_since():
    store = _seeded_store()
    assert store.spend_since("2020-01-01T00:00:00+00:00") == pytest.approx(
        220 / 1e6 * 1.0 + 60 / 1e6 * 2.0)
    assert store.spend_since("2999-01-01T00:00:00+00:00") == 0.0


def test_spend_since_treats_unpriced_calls_as_zero():
    store = TelemetryStore(":memory:")  # no prices -> cost is NULL
    MeteredLLM(UsageLLM(), store).summarize("t")
    assert store.spend_since("2020-01-01T00:00:00+00:00") == 0.0
