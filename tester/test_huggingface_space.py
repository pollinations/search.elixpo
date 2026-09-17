import json
from pathlib import Path
import sys

import pytest


SPACE = Path(__file__).resolve().parents[1] / "spaces" / "oreolook"
sys.path.insert(0, str(SPACE))

from oreolook_client import (  # noqa: E402
    OreoLookAPIError, extract_links, parse_sse, resolve_key, stream_completion,
)


def event(content, *, event_type=None):
    value = {"choices": [{"delta": {"content": content}}]}
    if event_type:
        value["event_type"] = event_type
    return "data: " + json.dumps(value)


class FakeResponse:
    def __init__(self, lines=(), status=200):
        self.lines = list(lines); self.status_code = status; self.closed = False
    def iter_lines(self, decode_unicode=True):
        assert decode_unicode is True
        return iter(self.lines)
    def close(self): self.closed = True


class FakeSession:
    def __init__(self, response): self.response = response; self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs)); return self.response


def test_sse_tasks_are_separate_and_reasoning_is_not_rendered():
    events = list(parse_sse([
        event("<TASK>Searching fresh sources</TASK>", event_type="INFO"),
        event("<thinking>private chain</thinking>"),
        event("Grounded answer "), event("with receipts."), "data: [DONE]",
    ]))
    assert [(item.kind, item.content) for item in events] == [
        ("task", "Searching fresh sources"),
        ("text", "Grounded answer "),
        ("text", "with receipts."),
    ]


def test_normal_keys_are_session_input_and_agent_tokens_are_rejected(monkeypatch):
    monkeypatch.delenv("POLLINATIONS_API_KEY", raising=False)
    assert resolve_key("sk_user") == "sk_user"
    with pytest.raises(OreoLookAPIError, match="Agent-run tokens"):
        resolve_key("ag_internal")
    with pytest.raises(OreoLookAPIError, match="Add your Pollinations"):
        resolve_key("")


@pytest.mark.parametrize(
    ("mode", "instruction"),
    [("Quick Search", "Use quick search"), ("Deep Research", "Use deep research")],
)
def test_stream_calls_pollinations_without_persisting_or_exposing_key(mode, instruction):
    response = FakeResponse([event("Hello"), "data: [DONE]"])
    session = FakeSession(response)
    messages = [{"role": "user", "content": "What changed today?"}]
    assert [item.content for item in stream_completion(
        messages, api_key="sk_private", mode=mode, session=session,
    )] == ["Hello"]
    url, call = session.calls[0]
    assert url == "https://gen.pollinations.ai/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk_private"
    assert call["json"]["store"] is False
    assert call["json"]["model"] == "Circuit-Overtime/OreoLook"
    assert instruction in call["json"]["messages"][-1]["content"]
    assert "sk_private" not in json.dumps(call["json"])
    assert messages == [{"role": "user", "content": "What changed today?"}]
    assert response.closed is True


def test_citations_and_pdf_artifacts_are_deduplicated_and_separated():
    text = (
        "See [Original report](https://example.com/report) and https://example.com/report. "
        "[Download PDF](https://search.elixpo.com/api/content/briefing.pdf?access=cap)."
    )
    sources, artifacts = extract_links(text)
    assert sources == [("Original report", "https://example.com/report")]
    assert artifacts == ["https://search.elixpo.com/api/content/briefing.pdf?access=cap"]


@pytest.mark.parametrize("status, phrase", [
    (401, "not accepted"), (403, "cannot access"), (429, "lot of love"), (503, "wobble"),
])
def test_upstream_failures_are_safe(status, phrase):
    session = FakeSession(FakeResponse(status=status))
    with pytest.raises(OreoLookAPIError, match=phrase):
        list(stream_completion(
            [{"role": "user", "content": "hello"}],
            api_key="sk_private", mode="Quick Search", session=session,
        ))
