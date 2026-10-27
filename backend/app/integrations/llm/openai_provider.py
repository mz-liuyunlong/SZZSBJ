"""OpenAI adapter: one provider boundary for billed model execution."""

from __future__ import annotations

from decimal import Decimal

from openai import AsyncOpenAI

NON_BILLABLE_HTTP_STATUS_CODES = frozenset({400, 401, 403, 404, 409, 422, 429})


def failed_call_reservation(reserved_cost: Decimal, status_code: int | None) -> tuple[Decimal, str]:
    """Release definite provider rejections; retain reservation for uncertain failures."""
    if status_code in NON_BILLABLE_HTTP_STATUS_CODES:
        return Decimal("0"), "AI_PROVIDER_REJECTED"
    return reserved_cost, "AI_PROVIDER_FAILURE"


async def generate_text(
    *, api_key: str, model: str, prompt: str, max_output_tokens: int,\n    visual_parts: list[dict[str, str]] | None = None,
) -> tuple[str, int, int]:
    async with AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0) as client:
        result = await client.responses.create(
            model=model,\n            input=([{\n                "role": "user",\n                "content": [{"type": "input_text", "text": prompt}, *(visual_parts or [])],\n            }] if visual_parts else prompt),\n            max_output_tokens=max_output_tokens
        )
    return (
        result.output_text,
        int(result.usage.input_tokens if result.usage else 0),
        int(result.usage.output_tokens if result.usage else 0),
    )
