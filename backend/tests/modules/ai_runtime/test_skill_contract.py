from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.ai_runtime.general_routes import SkillWrite
from app.modules.ai_runtime.provider import MAX_SKILL_INSTRUCTIONS


def test_skill_contract_matches_runtime_context_limit() -> None:
    valid = SkillWrite(
        connector_id=uuid4(),
        scene="keyword_launch",
        instructions="x" * MAX_SKILL_INSTRUCTIONS,
    )
    assert len(valid.instructions) == MAX_SKILL_INSTRUCTIONS

    with pytest.raises(ValidationError):
        SkillWrite(
            connector_id=uuid4(),
            scene="keyword_launch",
            instructions="x" * (MAX_SKILL_INSTRUCTIONS + 1),
        )
