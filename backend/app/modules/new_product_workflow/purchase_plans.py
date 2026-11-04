"""Create an approved, not-executed independent plan in the caller's transaction."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode


def create_independent_purchase_plan(
    session: Session,
    *,
    workflow_id: UUID,
    sku_identity_id: UUID,
    source_account_ref: str,
    quantity: int,
    market_score: int,
    rule_version: int,
    approval_workflow_version: int,
    approved_by: str,
    approval_note: str,
    purchase_reason: str,
) -> str:
    """Insert once; caller commits workflow, event and plan atomically."""
    if quantity <= 0 or len(approval_note.strip()) < 5:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
    plan_id = uuid4()
    number = f"NP-{plan_id.hex.upper()}"
    evidence = {
        "sku_identity_id": str(sku_identity_id),
        "source_account_ref": source_account_ref,
        "approved_quantity": quantity,
        "market_score": market_score,
        "rule_version": rule_version,
        "workflow_version": approval_workflow_version,
        "approved_by": approved_by,
        "approval_note": approval_note.strip(),
        "purchase_reason": purchase_reason,
        "formal_score_verified": False,
        "execution_status": "not_executed",
        "creates_pmc_order": False,
    }
    inserted = session.execute(
        text(
            """
            INSERT INTO product_new_purchase_plans
              (id, plan_number, workflow_id, sku_identity_id,
               source_account_ref, quantity, market_score, rule_version,
               approval_workflow_version, status, execution_status,
               approved_by, approval_note, snapshot_json)
            VALUES
              (:id, :number, :workflow, :sku,
               :account, :quantity, :score, :rules,
               :row_version, 'approved', 'not_executed',
               :actor, :note, CAST(:snapshot AS jsonb))
            ON CONFLICT (workflow_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "id": plan_id,
            "number": number,
            "workflow": workflow_id,
            "sku": sku_identity_id,
            "account": source_account_ref,
            "quantity": quantity,
            "score": market_score,
            "rules": rule_version,
            "row_version": approval_workflow_version,
            "actor": approved_by,
            "note": approval_note.strip(),
            "snapshot": json.dumps(evidence, ensure_ascii=False),
        },
    ).scalar_one_or_none()
    if inserted is None:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    return number
