"""Small, testable Pollinations streaming client used by the Gradio Space."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Iterable, Iterator, Mapping
from urllib.parse import urlparse

import requests


DEFAULT_BASE_URL = "https://gen.pollinations.ai/v1"
DEFAULT_MODEL = "Circuit-Overtime/OreoLook"
_TASK = re.compile(r"<TASK>(.*?)</TASK>", re.I | re.S)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BARE_URL = re.compile(r"(?<!\()https?://[^\s<>\]]+")
_PDF_URL = re.compile(r"https?://[^\s<>\])]+\.pdf(?:\?[^\s<>\])]*)?", re.I)


class OreoLookAPIError(RuntimeError):
    """Safe user-facing upstream error; never includes credentials."""


@dataclass(frozen=True, slots=True)
class StreamEvent:
    kind: str
    content: str


def resolve_key(user_key: str | None) -> str:
    key = (user_key or "").strip() or os.getenv("POLLINATIONS_API_KEY", "").strip()
    if not key:
        raise OreoLookAPIError(
            "Add your Pollinations API key in the sidebar to begin. It stays in this browser session."
        )
    if key.startswith("ag_"):
        raise OreoLookAPIError(
            "Agent-run tokens are internal and cannot be used here. Enter a normal Pollinations API key."
        )
    return key


def _mode_prompt(prompt: str, mode: str) -> str:
    if str(mode).lower().startswith("deep"):
        return (
            "Use deep research for this request. Investigate multiple relevant angles, verify current "
            "claims against sources, and synthesize a thorough cited answer.\n\n" + prompt.strip()
        )
    return (
        "Use quick search for this request. Prefer a fast, focused search with a concise cited answer.\n\n"
        + prompt.strip()
    )


def _safe_error(status: int) -> OreoLookAPIError:
    messages = {
        401: "That Pollinations API key was not accepted. Check the key and try again.",
        403: "This key cannot access OreoLook yet. Check its permissions or model availability.",
        429: "OreoLook is getting a lot of love right now. Please wait a moment and retry.",
    }
    if status in messages:
        return OreoLookAPIError(messages[status])
    if status >= 500:
        return OreoLookAPIError("OreoLook's upstream is having a wobble. Please try again shortly.")
    return OreoLookAPIError(f"The request could not be completed (HTTP {status}).")


def parse_sse(lines: Iterable[str | bytes]) -> Iterator[StreamEvent]:
    for raw in lines:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            event = json.loads(payload)
            delta = event["choices"][0].get("delta") or {}
            content = str(delta.get("content") or "")
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not content:
            continue
        task_match = _TASK.search(content)
        if event.get("event_type") == "INFO" or task_match:
            task = task_match.group(1).strip() if task_match else content.strip()
            if task and task.upper() != "DONE":
                yield StreamEvent("task", task)
            continue
        # Defensive last-mile suppression. OreoLook filters reasoning server-side;
        # the Space also drops any complete tagged block rather than displaying it.
        content = re.sub(r"<(thinking|reasoning|analysis)\b[^>]*>.*?</\1\s*>", "", content,
                         flags=re.I | re.S)
        if content:
            yield StreamEvent("text", content)


def stream_completion(
    messages: list[Mapping[str, str]], *, api_key: str | None, mode: str,
    timeout: tuple[float, float] = (10.0, 120.0), session=requests,
) -> Iterator[StreamEvent]:
    key = resolve_key(api_key)
    base_url = os.getenv("POLLINATIONS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("POLLINATIONS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    outbound = [dict(message) for message in messages]
    if not outbound or outbound[-1].get("role") != "user":
        raise OreoLookAPIError("Please enter a question first.")
    outbound[-1]["content"] = _mode_prompt(str(outbound[-1].get("content") or ""), mode)
    try:
        response = session.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model, "messages": outbound, "stream": True, "store": False,
                "metadata": {"oreolook_mode": "deep" if str(mode).lower().startswith("deep") else "quick"},
            },
            stream=True, timeout=timeout,
        )
    except requests.Timeout as exc:
        raise OreoLookAPIError("The request timed out before OreoLook could finish. Please retry.") from exc
    except requests.RequestException as exc:
        raise OreoLookAPIError("Could not reach Pollinations. Check your connection and retry.") from exc
    if response.status_code >= 400:
        response.close()
        raise _safe_error(response.status_code)
    try:
        yield from parse_sse(response.iter_lines(decode_unicode=True))
    finally:
        response.close()


def extract_links(markdown: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return unique source links and PDF artifacts without fetching either."""
    sources: list[tuple[str, str]] = []
    artifacts: list[str] = []
    seen_sources: set[str] = set()
    seen_artifacts: set[str] = set()
    labelled = {url: label.strip() or urlparse(url).netloc for label, url in _MARKDOWN_LINK.findall(markdown)}
    urls = [url for _, url in _MARKDOWN_LINK.findall(markdown)] + _BARE_URL.findall(markdown)
    for raw_url in urls:
        url = raw_url.rstrip(".,;:!?")
        if _PDF_URL.fullmatch(url):
            if url not in seen_artifacts:
                artifacts.append(url); seen_artifacts.add(url)
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen_sources:
            continue
        sources.append((labelled.get(url) or parsed.netloc.removeprefix("www."), url))
        seen_sources.add(url)
    return sources, artifacts
