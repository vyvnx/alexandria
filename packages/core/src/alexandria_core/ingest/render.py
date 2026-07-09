from math import ceil

from ..config import Settings, get_settings
from ..logging_config import get_logger

log = get_logger("render")

# height in px of each vertical slice handed to the VLM; keeps a very tall page
# from collapsing into one giant, low-detail image.
_SEGMENT_PX = 2000


def plan_segments(scroll_height: int, segment_px: int, max_segments: int) -> list[tuple[int, int]]:
    """Vertical (y_offset, height) clips covering a page of scroll_height px.

    ceil(scroll_height / segment_px) slices, capped at max_segments so the VLM
    cost is bounded on huge pages.
    """
    if scroll_height <= 0:
        return [(0, segment_px)]
    n = min(ceil(scroll_height / segment_px), max_segments)
    return [(i * segment_px, segment_px) for i in range(n)]


def screenshot(url: str, *, capture=None, settings: Settings | None = None) -> list[bytes]:
    """Return one or more PNG byte-strings for url, or [] on any failure.

    `capture` is injectable so tests never launch a real browser (mirrors the
    `fetch=` seam in load_url).
    """
    settings = settings or get_settings()
    capture = capture or _playwright_capture
    try:
        return capture(
            url,
            viewport_width=settings.screenshot_viewport_width,
            timeout_ms=settings.screenshot_timeout_ms,
            max_segments=settings.screenshot_max_segments,
        )
    except Exception as exc:  # never fail an ingest because a screenshot failed
        log.warning("screenshot failed for %s: %s", url, exc)
        return []


def _playwright_capture(url: str, *, viewport_width: int, timeout_ms: int,
                        max_segments: int) -> list[bytes]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": _SEGMENT_PX})
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            height = int(page.evaluate("document.body.scrollHeight") or _SEGMENT_PX)
            shots = []
            for y, h in plan_segments(height, _SEGMENT_PX, max_segments):
                shots.append(page.screenshot(
                    clip={"x": 0, "y": y, "width": viewport_width, "height": h}))
            return shots
        finally:
            browser.close()
