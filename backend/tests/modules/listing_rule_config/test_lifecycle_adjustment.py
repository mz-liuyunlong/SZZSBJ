"""Synthetic manual lifecycle decisions stay scoped, audited and atomic."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.permission_policy_v2 import permission_for_request
from app.modules.listing_rule_config import lifecycle_router
from app.modules.listing_rule_config.lifecycle import ListingLifecycleAdjustmentService
from app.modules.listing_rule_config.models import ListingLifecycleAdjustment

LISTING_ID = UUID(int=41)
ADJUSTMENT_ID = UUID(int=42)
ACCOUNTS = frozenset({"synthetic-account"})


def listing(stage: str | None = None):
    return SimpleNamespace(
        id=LISTING_ID,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        fulfillment_type="1",
        lifecycle_status=stage,
    )


def adjustment(stage: str | None = None):
    return ListingLifecycleAdjustment(
        id=ADJUSTMENT_ID,
        listing_id=LISTING_ID,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        expected_stage=stage,
        requested_stage="启动期",
        reason="synthetic evidence review",
        status="pending",
        requested_by="synthetic-requester",
        requested_at=datetime(2026, 1, 15, tzinfo=UTC),
    )


def test_request_records_prior_stage_without_writing_listing() -> None:
    session = MagicMock(spec=Session)
    current = listing("测品期")
    session.scalar.side_effect = [current, False]
    row = ListingLifecycleAdjustmentService(session).request(
        listing_id=LISTING_ID,
        requested_stage="启动期",
        reason="synthetic evidence review",
        actor="synthetic-requester",
        account_refs=ACCOUNTS,
    )
    assert row.expected_stage == "测品期"
    assert row.status == "pending"
    assert current.lifecycle_status == "测品期"
    session.commit.assert_called_once()


def test_separate_approver_commits_stage_and_decision_together() -> None:
    session = MagicMock(spec=Session)
    current = listing("测品期")
    request = adjustment("测品期")
    session.scalar.side_effect = [request, current, False]
    result = ListingLifecycleAdjustmentService(session).decide(
        adjustment_id=ADJUSTMENT_ID,
        approve=True,
        note="synthetic review accepted",
        actor="synthetic-approver",
        account_refs=ACCOUNTS,
    )
    assert result.status == "approved"
    assert result.decided_by == "synthetic-approver"
    assert current.lifecycle_status == "启动期"
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


@pytest.mark.parametrize("failure", ["same_actor", "stale_stage", "changed_account"])
def test_conflict_rolls_back_without_overwriting_listing(failure: str) -> None:
    session = MagicMock(spec=Session)
    current = listing("测品期")
    request = adjustment("测品期")
    if failure == "stale_stage":
        current.lifecycle_status = "稳定期"
    if failure == "changed_account":
        current.source_account_ref = "synthetic-other"
    session.scalar.side_effect = [request, current]
    actor = "synthetic-requester" if failure == "same_actor" else "synthetic-approver"
    with pytest.raises(ApiError):
        ListingLifecycleAdjustmentService(session).decide(
            adjustment_id=ADJUSTMENT_ID,
            approve=True,
            note="synthetic review accepted",
            actor=actor,
            account_refs=ACCOUNTS,
        )
    assert current.lifecycle_status != "启动期"
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_manual_write_routes_use_distinct_action_permissions() -> None:
    assert permission_for_request("POST", "/api/listings/lifecycle-adjustments", "") == (
        "action:products:listing-management:request-lifecycle"
    )
    assert (
        permission_for_request(
            "POST", f"/api/listings/lifecycle-adjustments/{ADJUSTMENT_ID}/decision", ""
        )
        == "action:products:listing-management:approve-lifecycle"
    )


def test_publication_flag_blocks_manual_writes_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        lifecycle_router,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_publish_enabled=False),
    )
    with pytest.raises(ApiError) as error:
        lifecycle_router._require_local_publication_enabled()
    assert error.value.code == "LISTING_EVALUATION_PUBLICATION_DISABLED"
