"""Compact paid-batch protocol: stable IDs, bounded context and strict validation."""

import json

import pytest

from app.modules.ai_runtime.compact_keyword_context import (
    build_semantic_prompt,
    make_semantic_batches,
    parse_semantic_result,
)


def test_999_keywords_require_40_batches_without_duplicate_context() -> None:
    keywords = [f"keyword {i}" for i in range(999)]
    batches = make_semantic_batches(keywords)
    assert len(batches) == 40
    assert sum(map(len, batches)) == 999
    prompt = build_semantic_prompt({"title": "organizer"}, ["competitor"], batches[0])
    assert '"title":"organizer"' in prompt
    assert '"0","keyword' not in prompt


def test_indexed_output_cannot_change_keyword_identity_or_order() -> None:
    keywords = ["one", "two"]
    result = parse_semantic_result(
        json.dumps({"rows": [[1, "L", "", "not supported"], [0, "H", "", "direct"]]}),
        keywords,
    )
    assert [row["keyword"] for row in result["items"]] == keywords
    assert [row["relevance"] for row in result["items"]] == ["high", "low"]


@pytest.mark.parametrize(
    "output",
    [
        {"rows": [[0, "H", "", ""], [0, "M", "", ""]]},
        {"rows": [[0, "H", "", ""]]},
        {"rows": [[0, "H", "", ""], [2, "L", "", ""]]},
        {"rows": [[0, "unknown", "", ""], [1, "L", "", ""]]},
    ],
)
def test_invalid_model_output_rejected(output: dict) -> None:
    with pytest.raises(ValueError, match="AI_RESPONSE_SCHEMA_INVALID"):
        parse_semantic_result(json.dumps(output), ["one", "two"])
