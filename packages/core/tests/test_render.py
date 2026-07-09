from alexandria_core.config import Settings
from alexandria_core.ingest.render import plan_segments, screenshot


def test_plan_segments_short_page_is_one_slice():
    assert plan_segments(500, 2000, 4) == [(0, 2000)]


def test_plan_segments_splits_tall_page():
    assert plan_segments(5000, 2000, 4) == [(0, 2000), (2000, 2000), (4000, 2000)]


def test_plan_segments_caps_at_max():
    assert len(plan_segments(20000, 2000, 4)) == 4


def test_screenshot_returns_empty_on_capture_error():
    def boom(url, **kw):
        raise RuntimeError("no browser")
    assert screenshot("http://x", capture=boom, settings=Settings(_env_file=None)) == []


def test_screenshot_passes_through_captured_bytes():
    def fake(url, **kw):
        return [b"PNGDATA"]
    assert screenshot("http://x", capture=fake, settings=Settings(_env_file=None)) == [b"PNGDATA"]
