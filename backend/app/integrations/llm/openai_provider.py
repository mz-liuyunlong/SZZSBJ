"""OpenAI adapter: one provider boundary for billed model execution."""

from __future__ import annotations

from openai import AsyncOpenAI


async def generate_text(
    *, api_key: str, model: str, prompt: str, max_output_tokens: int
) -> tuple[str, int, int]:
    async with AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0) as client:
        result = await client.responses.create(
            model=model, input=prompt, max_output_tokens=max_output_tokens
        )
    return (
        result.output_text,
        int(result.usage.input_tokens if result.usage else 0),
        int(result.usage.output_tokens if result.usage else 0),
    )
