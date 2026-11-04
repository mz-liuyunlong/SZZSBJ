"""Prove an approval plan is write-once, non-PMC, and never commits alone."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.api import ApiError
from app.modules.new_product_workflow.purchase_plans import create_independent_purchase_plan

SKU_ID = UUID("00000000-0000-0000-0000-000000000101")
WORKFLOW_ID = UUID("00000000-0000-0000-0000-000000000102")


def create(session: MagicMock, qty: int = 150) -> str:
    return create_independent_purchase_plan(
        session,
        workflow_id=WORKFLOW_ID,
        sku_identity_id=SKU_ID,
        source_account_ref="account-a",
        quantity=qty,
        market_score=8,
        rule_version=0,
        approval_workflow_version=3,
        approved_by="leader-1",
        approval_note="独立新品采购审批通过",
        purchase_reason="确认采购150件新品",
    )


def test_manual_approval_plan_contains_immutable_evidence_without_execution() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = WORKFLOW_ID
    number = create(session)
    stmt, params = session.execute.call_args.args
    evidence = json.loads(params["snapshot"])
    assert number.startswith("NP-")
    assert len(number) == 35
    assert params["account"] == "account-a"
    assert params["quantity"] == 150
    assert evidence["approved_quantity"] == 150
    assert evidence["formal_score_verified"] is False
    assert evidence["execution_status"] == "not_executed"
    assert evidence["creates_pmc_order"] is False
    assert "ON CONFLICT (workflow_id) DO NOTHING" in str(stmt)
    session.commit.assert_not_called()


def test_retry_cannot_insert_another_plan() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(ApiError) as error:
        create(session)
    assert error.value.status_code == 409
    session.commit.assert_not_called()


def test_invalid_quantity_never_reaches_database() -> None:
    session = MagicMock()
    with pytest.raises(ApiError) as error:
        create(session, 0)
    assert error.value.status_code == 422
    session.execute.assert_not_called()
