from alexandria_core.ingest.loaders import load_url, LoadedDoc

SAMPLE_HTML = """
<html><head><title>Attention Is All You Need</title>
<meta name="author" content="Vaswani et al."></head>
<body><article><h1>Attention Is All You Need</h1>
<p>The Transformer relies entirely on self-attention to compute representations.</p>
<p>It dispenses with recurrence and convolutions entirely.</p>
</article></body></html>
"""


def test_load_url_extracts_clean_text_and_title():
    doc = load_url("http://example.com/paper", fetch=lambda u: SAMPLE_HTML)
    assert isinstance(doc, LoadedDoc)
    assert "self-attention" in doc.text
    assert "Attention Is All You Need" in (doc.title or "")
    assert "<p>" not in doc.text          # HTML stripped


def test_load_url_handles_fetch_failure():
    doc = load_url("http://nope", fetch=lambda u: None)
    assert doc.text == "" and doc.title is None


# ── pdf loader (A2b) ─────────────────────────────────────────────────────────

def _pdf_bytes(text="Spaced repetition beats cramming."):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_load_pdf_extracts_the_text_layer():
    from alexandria_core.ingest.loaders import load_pdf
    doc = load_pdf(_pdf_bytes(), filename="notes.pdf")
    assert "Spaced repetition beats cramming." in doc.text
    assert doc.title == "notes.pdf"
    assert doc.url is None


def test_load_pdf_garbage_bytes_degrade_to_empty():
    from alexandria_core.ingest.loaders import load_pdf
    doc = load_pdf(b"this is not a pdf", filename="junk.pdf")
    assert doc.text == ""
