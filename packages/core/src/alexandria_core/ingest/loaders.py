from dataclasses import dataclass

from ..logging_config import get_logger

log = get_logger("scrape")


@dataclass
class LoadedDoc:
    url: str
    title: str | None
    author: str | None
    published_at: str | None
    text: str


def load_pdf(data: bytes, *, filename: str = "") -> LoadedDoc:
    """Digital-pdf loader (roadmap A2b): the text layer, page-joined, into the
    same LoadedDoc every other loader emits — the pipeline never knows the
    difference. Scanned pdfs (no text layer) come back empty; ocr is a
    deliberate non-feature until tesseract is installed."""
    import fitz

    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception:
        log.warning("unreadable pdf %r — not a pdf or corrupt", filename or "(upload)")
        return LoadedDoc(url=None, title=filename or None, author=None,
                         published_at=None, text="")
    try:
        text = "\n\n".join(page.get_text().strip() for page in pdf).strip()
        meta = pdf.metadata or {}
    finally:
        pdf.close()
    title = filename or meta.get("title") or None
    log.info("pdf %r: %d chars of text layer", title or "(untitled)", len(text))
    return LoadedDoc(url=None, title=title, author=meta.get("author") or None,
                     published_at=None, text=text)


def load_url(url: str, *, fetch=None) -> LoadedDoc:
    import trafilatura

    fetch = fetch or trafilatura.fetch_url
    log.info("fetching %s", url)
    html = fetch(url)
    if not html:
        log.warning("no HTML returned for %s (blocked, 404, or non-HTML)", url)
        return LoadedDoc(url=url, title=None, author=None, published_at=None, text="")
    log.debug("fetched %d bytes of HTML from %s", len(html), url)
    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    title = author = published = None
    try:
        meta = trafilatura.extract_metadata(html)
    except Exception:  # pragma: no cover - metadata is best-effort
        meta = None
    if meta is not None:
        title = getattr(meta, "title", None)
        author = getattr(meta, "author", None)
        published = getattr(meta, "date", None)
    log.info("pulled %r by %s (%s) — %d chars of text from %s",
             title or "(untitled)", author or "unknown", published or "no date",
             len(text), url)
    if text:
        log.debug("text preview: %s", text[:300].replace("\n", " "))
    return LoadedDoc(url=url, title=title, author=author, published_at=published, text=text)
