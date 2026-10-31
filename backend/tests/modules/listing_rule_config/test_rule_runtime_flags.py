"""The existing rule read reports runtime switches without enabling any task."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from app.modules.listing_rule_config import router
from app.modules.listing_rule_config.schemas import (
    ListingGradeRuleConfig,
    ListingGradeRuleRead,
    ListingGradeRuleUpdate,
)


@pytest.mark.parametrize("enabled", [False, True])
def test_rule_read_reports_actual_runtime_flags(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr(
        router,
        "get_settings",
        lambda: SimpleNamespace(
            listing_evaluation_preview_enabled=enabled,
            listing_evaluation_scheduler_enabled=enabled,
            listing_evaluation_publish_enabled=False,
        ),
    )
    monkeypatch.setattr(router, "has_permission", lambda _principal, _permission: False)
    monkeypatch.setattr(
        router.ListingGradeRuleService,
        "get",
        lambda _service, *, can_edit: ListingGradeRuleRead(
            version=0,
            config=ListingGradeRuleConfig(),
            source="default",
            can_edit=can_edit,
        ),
    )

    response = router.get_rule(Request({"type": "http", "headers": []}), Mock(), object())

    assert response.data.preview_enabled is enabled
    assert response.data.scheduler_enabled is enabled
    assert response.data.publish_enabled is False
    assert response.data.can_edit is False


def test_rule_save_response_keeps_runtime_status(monkeypatch) -> None:
    monkeypatch.setattr(
        router,
        "get_settings",
        lambda: SimpleNamespace(
            listing_evaluation_preview_enabled=True,
            listing_evaluation_scheduler_enabled=True,
            listing_evaluation_publish_enabled=False,
        ),
    )
    monkeypatch.setattr(
        router.ListingGradeRuleService,
        "update",
        lambda _service, *, request, actor: ListingGradeRuleRead(
            version=1,
            config=request.config,
            source="database",
            can_edit=True,
        ),
    )

    response = router.update_rule(
        Request({"type": "http", "headers": []}),
        ListingGradeRuleUpdate(
            expected_version=0,
            change_reason="synthetic rule change",
            config=ListingGradeRuleConfig(),
        ),
        Mock(),
        SimpleNamespace(user_id="synthetic-admin"),
    )

    assert response.data.scheduler_enabled is True
    assert response.data.preview_enabled is True
    assert response.data.publish_enabled is False
