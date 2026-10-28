"""AI runtime merge gates: pinned service and Skill, no UI/table mutation."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.ai_runtime.provider import (
    AIUnavailable,
    select_active_connector,
    select_published_skill,
)


def _connector(enabled_scene: str):
    return {
        "id": uuid4(),
        "config": {
            "default_model": "gpt-6-luna",
            "model_allowlist": ["gpt-6-luna"],
            "application_scenes": [enabled_scene],
        },
    }


def test_connector_is_explicitly_pinned_when_requested() -> None:
    row = _connector("keyword_launch")
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = row
    assert select_active_connector(session, "keyword_launch", row["id"]) == row
    sql = str(session.execute.call_args.args[0])
    assert "id=:connector" in sql
    assert session.execute.call_args.args[1] == {"connector": row["id"]}


def test_connector_must_grant_scene_and_model() -> None:
    row = _connector("ai_assistant")
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = row
    with pytest.raises(AIUnavailable, match="AI_SCENE_DISABLED"):
        select_active_connector(session, "keyword_launch", row["id"])


def test_skill_selection_is_scoped_to_connector() -> None:
    connector_id = uuid4()
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    assert select_published_skill(session, connector_id, "listing_optimization") is None
    sql = str(session.execute.call_args.args[0])
    params = session.execute.call_args.args[1]
    assert "connector_id=:connector" in sql
    assert "status='published'" in sql
    assert params == {"connector": connector_id, "scene": "listing_optimization"}


def test_missing_config_is_not_silently_replaced() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    with pytest.raises(AIUnavailable, match="AI_CONNECTOR_NOT_CONFIGURED"):
        select_active_connector(session, "keyword_launch")


def test_unpinned_selection_skips_services_without_requested_scene() -> None:
    first = _connector("ai_assistant")
    second = _connector("keyword_launch")
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [first, second]

    selected = select_active_connector(session, "keyword_launch")

    assert selected == second
    sql = str(session.execute.call_args.args[0])
    assert "ORDER BY created_at, id" in sql


def test_unpinned_selection_requires_a_matching_model_and_scene() -> None:
    wrong_model = _connector("keyword_launch")
    wrong_model["config"]["default_model"] = "gpt-4.1-mini"
    right_model_wrong_scene = _connector("ai_assistant")
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        wrong_model,
        right_model_wrong_scene,
    ]

    with pytest.raises(AIUnavailable, match="AI_MODEL_NOT_CONFIGURED"):
        select_active_connector(session, "keyword_launch")
