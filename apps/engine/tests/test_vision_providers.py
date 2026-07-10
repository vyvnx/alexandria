import base64

from engine.openai_provider import OpenAIProvider


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


def test_openai_describe_image_sends_image_and_prompt():
    seen = {}

    class _Comp:
        def create(self, **kw):
            seen.update(kw)
            return _FakeResp("A markdown table.")

    p = OpenAIProvider(api_key="sk", model="gpt-4o-mini")
    p.client = type("Client", (), {"chat": type("Chat", (), {"completions": _Comp()})()})()
    out = p.describe_image([b"PNG"], "read this")
    assert out == "A markdown table."
    content = seen["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "read this"}
    assert content[1]["type"] == "image_url"
    assert base64.b64encode(b"PNG").decode() in content[1]["image_url"]["url"]
