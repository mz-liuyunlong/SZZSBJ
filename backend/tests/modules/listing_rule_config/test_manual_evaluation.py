"""Synthetic checks for the permissioned all-Listing diagnostic request."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal
from app.core.permission_policy_v2 import permission_for_request
from app.modules.listing_rule_config import preview_router
from app.modules.listing_rule_config.tasks import account_scope_hash


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/listings/evaluation-runs/manual",
            "headers": [],
        }
    )


def test_manual_calculation_requires_distinct_action_permission() -> None:
    assert permission_for_request("POST", "/api/listings/evaluation-runs/manual", "") == (
        "action:products:listing-management:calculate-all"
    )
    assert account_scope_hash({"synthetic-b", "synthetic-a"}) == account_scope_hash(
        frozenset({"synthetic-a", "synthetic-b"})
    )


def test_manual_calculation_rejects_partial_account_scope(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = ["synthetic-a", "synthetic-b"]
    monkeypatch.setattr(
        preview_router,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_manual_enabled=True),
    )
    with pytest.raises(ApiError) as error:
        preview_router.request_manual_evaluation(
            request=_request(),
            _payload=preview_router.ManualEvaluationRequest(
                confirmation="CONFIRM_LISTING_CALCULATE_ALL"
            ),
            session=session,
            account_refs=frozenset({"synthetic-a"}),
            principal=Principal(user_id="synthetic-operator"),
        )
    assert error.value.code == "LISTING_EVALUATION_ALL_SCOPE_REQUIRED"
    session.add.assert_not_called()


def test_manual_calculation_queues_audited_diagnostic_only(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = ["synthetic-a"]
    session.scalar.return_value = None
    captured = []

    def record(row) -> None:
        row.id = UUID(int=17)
        captured.append(row)

    session.add.side_effect = record
    monkeypatch.setattr(
        preview_router,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_manual_enabled=True),
    )
    queued = []
    monkeypatch.setattr(
        preview_router.manual_diagnostic, "apply_async", lambda **kw: queued.append(kw)
    )
    result = preview_router.request_manual_evaluation(
        request=_request(),
        _payload=preview_router.ManualEvaluationRequest(
            confirmation="CONFIRM_LISTING_CALCULATE_ALL"
        ),
        session=session,
        account_refs=frozenset({"synthetic-a"}),
        principal=Principal(user_id="synthetic-operator"),
    )
    assert result.data.status == "queued"
    assert result.data.run_id is None
    assert result.data.cutoff_date_la <= datetime.now(UTC).date()
    assert captured[0].requested_by == "synthetic-operator"
    assert captured[0].account_scope_hash == account_scope_hash({"synthetic-a"})
    assert queued == [{"args": [str(UUID(int=17))]}]
    session.commit.assert_called_once()
