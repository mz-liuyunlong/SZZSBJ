"""Assistant-only streamed Responses API with optional model-managed web search.

No browser credentials are exposed.  Only real provider events are forwarded.
Other SZZSBJ AI scenes continue using the existing generate_text() adapter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from openai import AsyncOpenAI

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


def is_public_source(url: str) -> bool:
    """Only permit click-safe public HTTPS citations in client responses."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def extract_citations(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") != "message":
            continue
        for content in getattr(item, "content", []) or []:
            for note in getattr(content, "annotations", []) or []:
                if getattr(note, "type", "") != "url_citation":
                    continue
                url = getattr(note, "url", "")
                if not is_public_source(url) or url in seen:
                    continue
                seen.add(url)
                sources.append({"url": url, "title": str(getattr(note, "title", "") or url)[:200]})
                if len(sources) >= 12:
                    return sources
    return sources


async def generate_assistant_stream(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    visual_parts: list[dict[str, str]] | None,
    allow_web_search: bool,
    on_event: EventSink,
) -> tuple[str, int, int, bool, list[dict[str, str]], int]:
    """Stream text and true tool lifecycle events; return authoritative usage.

    Sending attachments disables web search to avoid transmitting attachment-derived
    private business details to the public web-search tool without separate consent.
    """
    model_input: Any = prompt
    if visual_parts:
        model_input = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    *visual_parts,
                ],
            }
        ]
    kwargs: dict[str, Any] = {}
    if allow_web_search:
        kwargs.update(tools=[{"type": "web_search"}], tool_choice="auto", max_tool_calls=2)
    chunks: list[str] = []
    completed: Any = None
    web_used = False
    observed_web_ids: set[str] = set()
    async with AsyncOpenAI(api_key=api_key, timeout=90.0, max_retries=0) as client:
        stream = await client.responses.create(
            model=model,
            input=model_input,
            max_output_tokens=max_output_tokens,
            stream=True,
            store=False,
            **kwargs,
        )
        async for event in stream:
            kind = getattr(event, "type", "")
            if kind in (
                "response.web_search_call.in_progress",
                "response.web_search_call.searching",
                "response.web_search_call.completed",
            ):
                observed_web_ids.add(str(getattr(event, "item_id", "")))
                if not web_used:
                    web_used = True
                    await on_event("searching", {})
            elif kind == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    chunks.append(delta)
                    await on_event("delta", {"text": delta})
            elif kind == "response.completed":
                completed = getattr(event, "response", None)
            elif kind in ("response.failed", "response.incomplete"):
                raise RuntimeError("AI_RESPONSE_NOT_COMPLETED")
    if completed is None or getattr(completed, "status", "") != "completed":
        raise RuntimeError("AI_RESPONSE_NOT_COMPLETED")
    answer = "".join(chunks)
    if not answer:
        for item in getattr(completed, "output", []) or []:
            if getattr(item, "type", "") == "message":
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", "") == "output_text":
                        answer += str(getattr(content, "text", ""))
        if answer:
            await on_event("delta", {"text": answer})
    if not answer.strip():
        raise RuntimeError("AI_EMPTY_RESPONSE")
    for item in getattr(completed, "output", []) or []:
        if getattr(item, "type", "") == "web_search_call":
            observed_web_ids.add(str(getattr(item, "id", "")))
    usage = getattr(completed, "usage", None)
    return (
        answer,
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
        web_used,
        extract_citations(completed),
        len(observed_web_ids),
    )
