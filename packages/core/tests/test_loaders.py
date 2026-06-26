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
