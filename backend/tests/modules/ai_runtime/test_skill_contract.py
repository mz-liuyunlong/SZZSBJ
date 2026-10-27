from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.ai_runtime.general_routes import SkillWrite
from app.modules.ai_runtime.provider import (
    MAX_SKILL_INSTRUCTIONS,
    MAX_SKILL_RUNTIME_INSTRUCTIONS,
    AIUnavailable,
    resolve_runtime_instructions,
)


def test_long_skill_reference_requires_compact_runtime_instructions() -> None:
    reference = "x" * 118_322
    valid = SkillWrite(
        connector_id=uuid4(),
        scene="keyword_launch",
        instructions=reference,
        runtime_instructions="compact rules",
    )
    assert len(valid.instructions) == 118_322
    assert (
        resolve_runtime_instructions(valid.instructions, valid.runtime_instructions)
        == "compact rules"
    )


def test_short_skill_remains_backward_compatible() -> None:
    assert resolve_runtime_instructions("short instructions", None) == "short instructions"


def test_long_skill_without_runtime_instructions_is_rejected() -> None:
    with pytest.raises(AIUnavailable, match="AI_SKILL_RUNTIME_INSTRUCTIONS_REQUIRED"):
        resolve_runtime_instructions("x" * 118_322, None)


def test_runtime_instructions_cannot_exceed_prompt_limit() -> None:
    with pytest.raises(ValidationError):
        SkillWrite(
            connector_id=uuid4(),
            scene="keyword_launch",
            instructions="reference",
            runtime_instructions="x" * (MAX_SKILL_RUNTIME_INSTRUCTIONS + 1),
        )


def test_reference_document_has_a_bounded_size() -> None:
    with pytest.raises(ValidationError):
        SkillWrite(
            connector_id=uuid4(),
            scene="keyword_launch",
            instructions="x" * (MAX_SKILL_INSTRUCTIONS + 1),
        )
