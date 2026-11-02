"""Streaming web-search protocol: deterministic provider fixtures, no outbound calls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.integrations.llm import assistant_web_stream as subject


def event(kind: str, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


@pytest.mark.asyncio
async def test_stream_reports_search_only_after_real_provider_event(monkeypatch) -> None:
    items = [
        event("response.web_search_call.searching", item_id="ws_test"),
        event("response.output_text.delta", delta="## Hello"),
        event("response.output_text.delta", delta=" world"),
        event(
            "response.completed",
            response=SimpleNamespace(
                status="completed",
                usage=SimpleNamespace(input_tokens=7, output_tokens=9),
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="## Hello world",
                                annotations=[
                                    SimpleNamespace(
                                        type="url_citation",
                                        url="https://example.com/page",
                                        title="Example",
                                    ),
                                    SimpleNamespace(
                                        type="url_citation", url="javascript:alert(1)", title="Bad"
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            ),
        ),
    ]
    captured = []

    class MockResponses:
        async def create(self, **kwargs):
            captured.append(kwargs)

            async def stream():
                for item in items:
                    yield item

            return stream()

    class MockClient:
        def __init__(self, **kwargs):
            self.responses = MockResponses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(subject, "AsyncOpenAI", MockClient)
    messages = []

    async def emit(kind, data):
        messages.append((kind, data))

    output = await subject.generate_assistant_stream(
        api_key="test-placeholder",
        model="gpt-6-luna",
        prompt="news",
        max_output_tokens=300,
        visual_parts=None,
        allow_web_search=True,
        on_event=emit,
    )
    assert output == (
        "## Hello world",
        7,
        9,
        True,
        [{"url": "https://example.com/page", "title": "Example"}],
        1,
    )
    assert messages[0] == ("searching", {})
    assert messages[1] == ("delta", {"text": "## Hello"})
    assert captured[0]["tools"] == [{"type": "web_search"}]
    assert captured[0]["tool_choice"] == "auto"
    assert captured[0]["max_tool_calls"] == 2
    assert captured[0]["store"] is False


def test_citation_restricts_unsafe_links() -> None:
    assert subject.is_public_source("https://example.com")
    assert not subject.is_public_source("javascript:alert(1)")
    assert not subject.is_public_source("file:///etc/passwd")
    assert not subject.is_public_source("http://example.com")


@pytest.mark.asyncio
async def test_failed_stream_is_rejected_instead_of_reporting_partial_success(monkeypatch) -> None:
    class MockResponses:
        async def create(self, **kwargs):
            async def stream():
                yield event("response.output_text.delta", delta="partial")
                yield event("response.failed")

            return stream()

    class MockClient:
        def __init__(self, **kwargs):
            self.responses = MockResponses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(subject, "AsyncOpenAI", MockClient)
    received = []

    async def emit(kind, data):
        received.append((kind, data))

    with pytest.raises(RuntimeError, match="AI_RESPONSE_NOT_COMPLETED"):
        await subject.generate_assistant_stream(
            api_key="test-placeholder",
            model="gpt-6-luna",
            prompt="test",
            max_output_tokens=128,
            visual_parts=None,
            allow_web_search=False,
            on_event=emit,
        )
    assert received == [("delta", {"text": "partial"})]
