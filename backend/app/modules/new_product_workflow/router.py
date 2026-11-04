"""Account-scoped new-product draft workflow.

The approval state is a draft decision only. This module intentionally does not
create PMC plans, issue purchase orders, or invent attribution/advertising metrics.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.data_pages.field_access import (
    ORDER_PROFIT_GROSS_PROFIT_PERMISSION,
    ORDER_PROFIT_MARGIN_PERMISSION,
)
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.new_product_workflow.dashboard import read_new_product_dashboard
from app.modules.new_product_workflow.field_access import redact_new_product_metrics
from app.modules.new_product_workflow.metrics import la_today, read_sku_metrics
from app.modules.new_product_workflow.purchase_plans import create_independent_purchase_plan
from app.modules.new_product_workflow.rules import DEFAULT_RULES

VIEW = "page:products:new-product-analysis:view"
TRACK_VIEW = "page:products:launch-tracking:view"
SCORE = "action:products:new-product-analysis:score"
REQUEST = "action:products:new-product-analysis:request-purchase"
APPROVE = "action:products:new-product-analysis:approve"
REVIEW = "action:products:launch-tracking:review"
CONFIGURE = "action:products:new-product-analysis:configure"

router = APIRouter(prefix="/api/new-products", tags=["New Product Draft Workflow"])
db_session = Annotated[Session, Depends(get_db_session)]
account_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view_principal = Annotated[Principal, Depends(require_any_permission(VIEW, TRACK_VIEW))]


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def reject_blank_evidence(self) -> StrictPayload:
        # Field min_length counts whitespace; audit evidence must be substantive.
        for field in ("reason", "note", "evidence"):
            value = getattr(self, field, None)
            if isinstance(value, str) and len(value.strip()) < 5:
                raise ValueError(f"{field} requires at least five non-whitespace characters")
        return self


class VersionedPayload(StrictPayload):
    expected_version: int = Field(ge=0)


class MarketWrite(VersionedPayload):
    score: int = Field(ge=0, le=10)
    reason: str = Field(min_length=5, max_length=1000)


class PurchaseWrite(VersionedPayload):
    quantity: int = Field(gt=0, le=1000000)
    reason: str = Field(min_length=5, max_length=1000)


class DecisionWrite(VersionedPayload):
    decision: Literal["approved_draft", "rejected"]
    note: str = Field(min_length=5, max_length=1000)


class ReviewWrite(VersionedPayload):
    result: Literal["observe", "optimize"]
    reason: str = Field(min_length=5, max_length=1000)
    next_review: date | None = None

    @model_validator(mode="after")
    def check_next_review(self) -> ReviewWrite:
        if self.result == "optimize" and self.next_review is None:
            raise ValueError("optimization requires the next review date")
        return self


class LaunchDateWrite(VersionedPayload):
    arrival_date: date
    sellable_date: date
    evidence: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def verify_actual_dates(self) -> LaunchDateWrite:
        if max(self.arrival_date, self.sellable_date) > la_today():
            raise ValueError("Actual arrival and sellable dates cannot be in the future")
        return self


class ScoreCorrectionWrite(VersionedPayload):
    dimension: Literal["order", "ads", "profit", "trust"]
    target_score: float = Field(ge=0, le=10)
    reason: str = Field(min_length=5, max_length=1000)


class ScoreCorrectionDecision(StrictPayload):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=5, max_length=1000)


class RuleWrite(StrictPayload):
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=1000)
    weights: dict[Literal["market", "order", "ads", "profit", "trust"], int]
    success_days: Literal[30, 60, 90]
    min_sales: int = Field(gt=0)
    min_margin: float = Field(ge=-100, le=100)
    max_acos: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def check_weights(self) -> RuleWrite:
        if len(self.weights) != 5 or sum(self.weights.values()) != 100:
            raise ValueError("all five weights must add up to 100")
        if any(value < 0 or value > 100 for value in self.weights.values()):
            raise ValueError("weight values must be between 0 and 100")
        return self


def _block(status: int, code: ErrorCode = ErrorCode.INVALID_REQUEST) -> None:
    raise ApiError(code=code, status_code=status)


def _identity(session: Session, sku_id: UUID, scope: frozenset[str]) -> dict[str, Any]:
    identity = (
        session.execute(
            text("""
            SELECT id, source_account_ref, lingxing_sku_code
            FROM dwd_lingxing_sku_identity_index
            WHERE id = :id AND source_account_ref = ANY(:accounts)
              AND is_active IS TRUE
        """),
            {"id": sku_id, "accounts": sorted(scope)},
        )
        .mappings()
        .first()
    )
    if identity is None:
        _block(404, ErrorCode.NOT_FOUND)
    return dict(identity)


def _state(session: Session, sku_id: UUID, *, lock: bool) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock else ""
    row = (
        session.execute(
            text("SELECT * FROM product_new_workflows WHERE sku_identity_id = :id" + suffix),
            {"id": sku_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return {
            "id": None,
            "sku_identity_id": sku_id,
            "status": "pending_market",
            "row_version": 0,
            "market_score": None,
            "market_reason": None,
            "purchase_request_qty": None,
            "purchase_reason": None,
            "purchase_review_by": None,
            "purchase_review_at": None,
            "purchase_review_note": None,
            "review_result": None,
            "review_reason": None,
            "review_due_at": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "score_snapshot_json": None,
            "arrival_date": None,
            "sellable_date": None,
            "date_evidence": None,
            "dates_verified_by": None,
            "dates_verified_at": None,
        }
    return dict(row)


def _edit(
    session: Session,
    sku_id: UUID,
    scope: frozenset[str],
    principal: Principal,
    request: Request,
    payload: VersionedPayload,
    action: str,
) -> dict[str, Any]:
    identity = _identity(session, sku_id, scope)
    before = _state(session, sku_id, lock=True)
    if before["row_version"] != payload.expected_version:
        _block(409)
    status = before["status"]
    changes: dict[str, Any] = {}
    reason = ""
    if isinstance(payload, MarketWrite):
        if status != "pending_market":
            _block(409)
        reason = payload.reason.strip()
        changes = {"market_score": payload.score, "market_reason": reason, "status": "scored"}
    elif isinstance(payload, PurchaseWrite):
        if status not in ("scored", "rejected") or before["market_score"] is None:
            _block(409)
        reason = payload.reason.strip()
        changes = {
            "purchase_request_qty": payload.quantity,
            "purchase_reason": reason,
            "status": "pending_purchase",
        }
    elif isinstance(payload, DecisionWrite):
        if status != "pending_purchase" or not before["purchase_request_qty"]:
            _block(409)
        pending = session.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM product_new_score_corrections "
                "WHERE sku_identity_id = :sku AND status = 'pending')"
            ),
            {"sku": sku_id},
        ).scalar_one()
        if pending:
            _block(409)
        reason = payload.note.strip()
        changes = {
            "purchase_review_by": principal.user_id,
            "purchase_review_at": None,
            "purchase_review_note": reason,
            "status": payload.decision,
        }
        if payload.decision == "approved_draft":
            rule_version = session.execute(
                text("SELECT COALESCE(MAX(version), 0) FROM product_new_rule_versions")
            ).scalar_one()
            evidence = {
                "kind": "draft_evidence_only",
                "sku_identity_id": str(sku_id),
                "source_account_ref": identity["source_account_ref"],
                "market_score": before["market_score"],
                "purchase_request_qty": before["purchase_request_qty"],
                "rule_version": int(rule_version),
                "approved_by": principal.user_id,
                "has_verified_ads_inventory_metrics": False,
                "creates_pmc_order": False,
            }
            changes["score_snapshot_json"] = json.dumps(evidence)
    elif isinstance(payload, LaunchDateWrite):
        if status != "approved_draft":
            _block(409)
        reason = payload.evidence.strip()
        changes = {
            "arrival_date": payload.arrival_date,
            "sellable_date": payload.sellable_date,
            "date_evidence": reason,
            "dates_verified_by": principal.user_id,
        }
    elif isinstance(payload, ReviewWrite):
        if status != "approved_draft":
            _block(409)
        reason = payload.reason.strip()
        changes = {
            "review_result": payload.result,
            "review_reason": reason,
            "review_due_at": payload.next_review,
            "reviewed_by": principal.user_id,
        }
    else:
        _block(422)

    if before["id"] is None:
        workflow_id = uuid4()
        session.execute(
            text("""
                INSERT INTO product_new_workflows
                  (id, sku_identity_id, source_account_ref, status, market_score,
                   market_reason, row_version)
                VALUES
                  (:id, :sku_id, :account, :status, :score, :reason, 1)
                ON CONFLICT (sku_identity_id) DO NOTHING
            """),
            {
                "id": workflow_id,
                "sku_id": sku_id,
                "account": identity["source_account_ref"],
                "status": changes["status"],
                "score": changes["market_score"],
                "reason": changes["market_reason"],
            },
        )
        after = _state(session, sku_id, lock=True)
        if after["id"] != workflow_id:
            _block(409)
    else:
        assignments = ", ".join(
            f"{key} = CAST(:{key} AS jsonb)" if key == "score_snapshot_json" else f"{key} = :{key}"
            for key in changes
        )
        now_fields = []
        if isinstance(payload, DecisionWrite):
            now_fields.append("purchase_review_at = now()")
        if isinstance(payload, ReviewWrite):
            now_fields.append("reviewed_at = now()")
        if isinstance(payload, LaunchDateWrite):
            now_fields.append("dates_verified_at = now()")
        clause = ", ".join(
            [assignments, *now_fields, "row_version = row_version + 1", "updated_at = now()"]
        )
        session.execute(
            text(f"UPDATE product_new_workflows SET {clause} WHERE id = :id"),
            {"id": before["id"], **changes},
        )
        after = _state(session, sku_id, lock=False)

    if isinstance(payload, DecisionWrite) and payload.decision == "approved_draft":
        # Both the independent plan and the audit event commit with the approval.
        number = create_independent_purchase_plan(
            session,
            workflow_id=after["id"],
            sku_identity_id=sku_id,
            source_account_ref=identity["source_account_ref"],
            quantity=int(before["purchase_request_qty"]),
            market_score=int(before["market_score"]),
            rule_version=int(rule_version),
            approval_workflow_version=int(after["row_version"]),
            approved_by=principal.user_id,
            approval_note=reason,
            purchase_reason=before["purchase_reason"] or "",
        )
        after = {**after, "plan_number": number}

    session.execute(
        text("""
            INSERT INTO product_new_workflow_events
              (id, workflow_id, action, actor, reason, before_json, after_json, request_id)
            VALUES
              (:id, :workflow_id, :action, :actor, :reason,
               CAST(:before_json AS jsonb), CAST(:after_json AS jsonb), :request_id)
        """),
        {
            "id": uuid4(),
            "workflow_id": after["id"],
            "action": action,
            "actor": principal.user_id,
            "reason": reason,
            "before_json": json.dumps(before, default=str),
            "after_json": json.dumps(after, default=str),
            "request_id": get_request_id(request),
        },
    )
    session.commit()
    return after



def _approved_corrections(session: Session, sku_id: UUID) -> dict[str, float]:
    rows = (
        session.execute(
            text(
                """
                SELECT DISTINCT ON (dimension) dimension, requested_score
                FROM product_new_score_corrections
                WHERE sku_identity_id = :sku AND status = 'approved'
                ORDER BY dimension, reviewed_at DESC, id DESC
                """
            ),
            {"sku": sku_id},
        )
        .mappings()
        .all()
    )
    return {row["dimension"]: float(row["requested_score"]) for row in rows}


def _financial_correction_allowed(principal: Principal, dimension: str) -> bool:
    if dimension != "profit":
        return True
    return has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION) and (
        has_permission(principal, ORDER_PROFIT_MARGIN_PERMISSION)
    )


@router.get("/dashboard", response_model=SuccessEnvelope[dict[str, Any], None])
def get_new_product_dashboard(
    request: Request,
    session: db_session,
    _: view_principal,
    accounts: account_scope,
    source_account_ref: str = Query(min_length=1, max_length=128),
) -> SuccessEnvelope[dict[str, Any], None]:
    if source_account_ref not in accounts:
        _block(403, ErrorCode.DATA_SCOPE_DENIED)
    return success_response(
        request,
        data=read_new_product_dashboard(session, account=source_account_ref),
    )


@router.get("/score-corrections", response_model=SuccessEnvelope[dict[str, Any], None])
def list_score_corrections(
    request: Request,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
    source_account_ref: str = Query(min_length=1, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SuccessEnvelope[dict[str, Any], None]:
    if source_account_ref not in accounts:
        _block(403, ErrorCode.DATA_SCOPE_DENIED)
    allow_profit = _financial_correction_allowed(principal, "profit")
    params = {
        "account": source_account_ref,
        "allow_profit": allow_profit,
        "skip": (page - 1) * page_size,
        "size": page_size,
    }
    where = (
        "WHERE source_account_ref = :account "
        "AND (:allow_profit OR dimension <> 'profit')"
    )
    count = session.execute(
        text("SELECT count(*) FROM product_new_score_corrections " + where),
        params,
    ).scalar_one()
    rows = (
        session.execute(
            text(
                "SELECT id, sku_identity_id, source_account_ref, dimension, "
                "from_score, requested_score, rule_version, status, "
                "reason, requested_by, reviewed_by, review_note, created_at, "
                "reviewed_at FROM product_new_score_corrections "
                + where
                + " ORDER BY created_at DESC, id DESC LIMIT :size OFFSET :skip"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return success_response(
        request,
        data={"items": [dict(row) for row in rows], "total": int(count), "page": page},
    )


@router.post(
    "/workflows/{sku_id}/score-correction",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def request_score_correction(
    request: Request,
    sku_id: UUID,
    payload: ScoreCorrectionWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(SCORE))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    identity = _identity(session, sku_id, accounts)
    before = _state(session, sku_id, lock=True)
    if (
        before["id"] is None
        or before["row_version"] != payload.expected_version
        or before["status"] not in ("scored", "pending_purchase", "rejected")
    ):
        _block(409)
    if not _financial_correction_allowed(principal, payload.dimension):
        _block(403)
    rule = (
        session.execute(
            text(
                "SELECT version, rule_json FROM product_new_rule_versions "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    metrics = read_sku_metrics(
        session,
        account=identity["source_account_ref"],
        sku=identity["lingxing_sku_code"],
        market_score=before["market_score"],
        rule_version=int(rule["version"]) if rule else 0,
        rules=dict(rule["rule_json"]) if rule else DEFAULT_RULES,
        score_overrides=_approved_corrections(session, sku_id),
    )
    components = metrics["score"].get("components", {})
    original = components.get(payload.dimension)
    if original is None or abs(float(original) - payload.target_score) < 0.01:
        _block(422)
    correction_id = uuid4()
    evidence = {
        "account": identity["source_account_ref"],
        "sku_identity_id": str(sku_id),
        "dimension": payload.dimension,
        "before": float(original),
        "requested": payload.target_score,
        "rule_version": metrics["rule_version"],
        "as_of_exclusive": metrics["as_of_exclusive"],
        "data_issues": metrics["periods"]["30"]["data_issues"],
        "formal_grade_approved": False,
    }
    inserted = session.execute(
        text(
            """
            INSERT INTO product_new_score_corrections
              (id, workflow_id, sku_identity_id, source_account_ref,
               dimension, from_score, requested_score, rule_version,
               status, reason, requested_by, evidence_json)
            VALUES
              (:id, :workflow, :sku, :account, :dimension,
               :original, :requested, :rule_version, 'pending',
               :reason, :actor, CAST(:evidence AS jsonb))
            ON CONFLICT DO NOTHING RETURNING id
            """
        ),
        {
            "id": correction_id,
            "workflow": before["id"],
            "sku": sku_id,
            "account": identity["source_account_ref"],
            "dimension": payload.dimension,
            "original": float(original),
            "requested": payload.target_score,
            "rule_version": metrics["rule_version"],
            "reason": payload.reason.strip(),
            "actor": principal.user_id,
            "evidence": json.dumps(evidence),
        },
    ).scalar_one_or_none()
    if inserted is None:
        _block(409)
    session.execute(
        text(
            "UPDATE product_new_workflows SET row_version = row_version + 1, "
            "updated_at = now() WHERE id = :workflow"
        ),
        {"workflow": before["id"]},
    )
    session.execute(
        text(
            """
            INSERT INTO product_new_workflow_events
              (id, workflow_id, action, actor, reason, before_json, after_json, request_id)
            VALUES
              (:id, :workflow, 'correction_requested', :actor, :reason,
               CAST(:before AS jsonb), CAST(:after AS jsonb), :request)
            """
        ),
        {
            "id": uuid4(),
            "workflow": before["id"],
            "actor": principal.user_id,
            "reason": payload.reason.strip(),
            "before": json.dumps({"dimension": payload.dimension, "value": original}),
            "after": json.dumps(evidence),
            "request": get_request_id(request),
        },
    )
    session.commit()
    return success_response(
        request,
        data={"id": correction_id, "status": "pending", "formal_grade": None},
    )


@router.post(
    "/score-corrections/{correction_id}/decision",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def decide_score_correction(
    request: Request,
    correction_id: UUID,
    payload: ScoreCorrectionDecision,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(APPROVE))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    row = (
        session.execute(
            text(
                "SELECT * FROM product_new_score_corrections WHERE id = :id "
                "AND source_account_ref = ANY(:accounts) FOR UPDATE"
            ),
            {"id": correction_id, "accounts": sorted(accounts)},
        )
        .mappings()
        .first()
    )
    if row is None:
        _block(404, ErrorCode.NOT_FOUND)
    if row["status"] != "pending" or row["requested_by"] == principal.user_id:
        _block(409)
    if not _financial_correction_allowed(principal, row["dimension"]):
        _block(403)
    state = _state(session, row["sku_identity_id"], lock=True)
    if state["status"] not in ("scored", "pending_purchase", "rejected"):
        _block(409)
    saved = session.execute(
        text(
            "UPDATE product_new_score_corrections SET status = :decision, "
            "reviewed_by = :actor, review_note = :note, reviewed_at = now() "
            "WHERE id = :id AND status = 'pending' RETURNING id"
        ),
        {
            "id": correction_id,
            "decision": payload.decision,
            "actor": principal.user_id,
            "note": payload.note.strip(),
        },
    ).scalar_one_or_none()
    if saved is None:
        _block(409)
    # A corrected score invalidates a pending quantity request.
    clear_purchase = payload.decision == "approved" and state["status"] == "pending_purchase"
    if clear_purchase:
        session.execute(
            text(
                "UPDATE product_new_workflows SET status = 'scored', "
                "purchase_request_qty = NULL, purchase_reason = NULL, "
                "row_version = row_version + 1, updated_at = now() WHERE id = :id"
            ),
            {"id": state["id"]},
        )
    else:
        session.execute(
            text(
                "UPDATE product_new_workflows SET row_version = row_version + 1, "
                "updated_at = now() WHERE id = :id"
            ),
            {"id": state["id"]},
        )
    session.execute(
        text(
            """
            INSERT INTO product_new_workflow_events
              (id, workflow_id, action, actor, reason, before_json, after_json, request_id)
            VALUES
              (:id, :workflow, 'correction_decided', :actor, :reason,
               CAST(:before AS jsonb), CAST(:after AS jsonb), :request)
            """
        ),
        {
            "id": uuid4(),
            "workflow": state["id"],
            "actor": principal.user_id,
            "reason": payload.note.strip(),
            "before": json.dumps({"correction_id": str(correction_id), "status": "pending"}),
            "after": json.dumps(
                {
                    "correction_id": str(correction_id),
                    "status": payload.decision,
                    "purchase_request_invalidated": clear_purchase,
                    "formal_score_approved": False,
                }
            ),
            "request": get_request_id(request),
        },
    )
    session.commit()
    return success_response(
        request,
        data={
            "id": correction_id,
            "status": payload.decision,
            "purchase_request_invalidated": clear_purchase,
        },
    )


@router.get("/rules/history", response_model=SuccessEnvelope[dict[str, Any], None])
def list_rule_history(
    request: Request,
    session: db_session,
    _: view_principal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SuccessEnvelope[dict[str, Any], None]:
    total = session.execute(
        text("SELECT count(*) FROM product_new_rule_versions")
    ).scalar_one()
    rows = (
        session.execute(
            text(
                "SELECT version, actor, reason, created_at, rule_json "
                "FROM product_new_rule_versions "
                "ORDER BY version DESC LIMIT :size OFFSET :skip"
            ),
            {"size": page_size, "skip": (page - 1) * page_size},
        )
        .mappings()
        .all()
    )
    return success_response(
        request, data={"items": [dict(row) for row in rows], "total": int(total)}
    )


@router.get("/source-accounts", response_model=SuccessEnvelope[dict[str, Any], None])
def list_source_accounts(
    request: Request,
    _: view_principal,
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    """Only account refs permitted by the same data scope used for reads and writes."""
    return success_response(request, data={"items": sorted(accounts)})


@router.get("/workflows", response_model=SuccessEnvelope[dict[str, Any], None])
def list_workflows(
    request: Request,
    session: db_session,
    _: view_principal,
    accounts: account_scope,
    source_account_ref: str = Query(min_length=1, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SuccessEnvelope[dict[str, Any], None]:
    if source_account_ref not in accounts:
        _block(403, ErrorCode.DATA_SCOPE_DENIED)
    params = {"account": source_account_ref, "size": page_size, "skip": (page - 1) * page_size}
    total = session.execute(
        text("""
        SELECT count(*) FROM dwd_lingxing_sku_identity_index
        WHERE source_account_ref = :account AND is_active IS TRUE
    """),
        {"account": source_account_ref},
    ).scalar_one()
    rows = (
        session.execute(
            text("""
        SELECT identity.id AS sku_identity_id, identity.lingxing_sku_code AS sku,
               identity.source_account_ref,
               COALESCE(p.product_name, detail.product_name) AS product_name,
               p.category, detail.product_developer_name AS developer,
               detail.owner_name AS operator, detail.source_observed_at AS product_observed_at,
               workflow.id AS workflow_id, workflow.status,
               workflow.row_version, workflow.market_score, workflow.market_reason,
               workflow.purchase_request_qty, workflow.purchase_reason,
               workflow.purchase_review_by, workflow.purchase_review_at,
               workflow.review_result, workflow.review_reason,
               workflow.review_due_at, workflow.reviewed_by, workflow.reviewed_at,
               workflow.arrival_date, workflow.sellable_date,
               workflow.date_evidence, workflow.dates_verified_by, workflow.dates_verified_at,
               plan.plan_number, plan.id AS plan_id,
               plan.execution_status AS plan_execution_status
        FROM dwd_lingxing_sku_identity_index AS identity
        LEFT JOIN products AS p ON p.id = identity.product_id AND p.deleted_at IS NULL
        LEFT JOIN dwd_lingxing_sku_product_info_current AS detail
          ON detail.identity_id = identity.id
         AND detail.source_account_ref = identity.source_account_ref
        LEFT JOIN product_new_workflows AS workflow
          ON workflow.sku_identity_id = identity.id
         AND workflow.source_account_ref = identity.source_account_ref
        LEFT JOIN product_new_purchase_plans AS plan
          ON plan.workflow_id = workflow.id
         AND plan.source_account_ref = identity.source_account_ref
        WHERE identity.source_account_ref = :account AND identity.is_active IS TRUE
        ORDER BY identity.id LIMIT :size OFFSET :skip
    """),
            params,
        )
        .mappings()
        .all()
    )
    return success_response(
        request, data={"items": [dict(row) for row in rows], "page": page, "total": int(total)}
    )


@router.get("/purchase-plans", response_model=SuccessEnvelope[dict[str, Any], None])
def list_independent_purchase_plans(
    request: Request,
    session: db_session,
    _: view_principal,
    accounts: account_scope,
    source_account_ref: str = Query(min_length=1, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SuccessEnvelope[dict[str, Any], None]:
    if source_account_ref not in accounts:
        _block(403, ErrorCode.DATA_SCOPE_DENIED)
    params = {"account": source_account_ref, "size": page_size, "skip": (page - 1) * page_size}
    total = session.execute(
        text("SELECT count(*) FROM product_new_purchase_plans WHERE source_account_ref = :account"),
        {"account": source_account_ref},
    ).scalar_one()
    rows = (
        session.execute(
            text(
                """
                SELECT plan.id, plan.plan_number, plan.sku_identity_id,
                       plan.source_account_ref, identity.lingxing_sku_code AS sku,
                       plan.quantity, plan.status, plan.execution_status,
                       plan.market_score, plan.rule_version, plan.approved_by,
                       plan.approval_note, plan.created_at,
                       plan.approval_workflow_version
                FROM product_new_purchase_plans AS plan
                JOIN dwd_lingxing_sku_identity_index AS identity
                  ON identity.id = plan.sku_identity_id
                 AND identity.source_account_ref = plan.source_account_ref
                WHERE plan.source_account_ref = :account
                ORDER BY plan.created_at DESC, plan.id DESC
                LIMIT :size OFFSET :skip
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return success_response(
        request, data={"items": [dict(row) for row in rows], "page": page, "total": int(total)}
    )


@router.get("/purchase-plans/{plan_id}", response_model=SuccessEnvelope[dict[str, Any], None])
def get_independent_purchase_plan(
    request: Request,
    plan_id: UUID,
    session: db_session,
    _: view_principal,
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    """No cross-account disclosure of saved approval snapshots."""
    row = (
        session.execute(
            text(
                """
                SELECT id, plan_number, sku_identity_id, source_account_ref,
                       quantity, status, execution_status, market_score,
                       rule_version, approval_workflow_version, approved_by,
                       approval_note, snapshot_json, created_at
                FROM product_new_purchase_plans
                WHERE id = :id AND source_account_ref = ANY(:accounts)
                """
            ),
            {"id": plan_id, "accounts": sorted(accounts)},
        )
        .mappings()
        .first()
    )
    if row is None:
        _block(404, ErrorCode.NOT_FOUND)
    return success_response(request, data=dict(row))


@router.get("/workflows/{sku_id}", response_model=SuccessEnvelope[dict[str, Any], None])
def get_workflow(
    request: Request,
    sku_id: UUID,
    session: db_session,
    _: view_principal,
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    identity = _identity(session, sku_id, accounts)
    return success_response(request, data={**identity, **_state(session, sku_id, lock=False)})


@router.get("/workflows/{sku_id}/metrics", response_model=SuccessEnvelope[dict[str, Any], None])
def get_workflow_metrics(
    request: Request,
    sku_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    identity = _identity(session, sku_id, accounts)
    sku = identity["lingxing_sku_code"]
    if not sku:
        _block(422)
    state = _state(session, sku_id, lock=False)
    rule = (
        session.execute(
            text(
                "SELECT version, rule_json FROM product_new_rule_versions "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    verified_start = (
        max(state["arrival_date"], state["sellable_date"])
        if state["arrival_date"] and state["sellable_date"] and state["dates_verified_by"]
        else None
    )
    overrides = _approved_corrections(session, sku_id)
    metrics = read_sku_metrics(
        session,
        account=identity["source_account_ref"],
        sku=sku,
        market_score=state["market_score"],
        rule_version=int(rule["version"]) if rule else 0,
        rules=dict(rule["rule_json"]) if rule else DEFAULT_RULES,
        start_date=verified_start,
        score_overrides=overrides,
    )
    return success_response(
        request,
        data=redact_new_product_metrics(metrics, principal),
    )


@router.post(
    "/workflows/{sku_id}/market",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def set_market(
    request: Request,
    sku_id: UUID,
    payload: MarketWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(SCORE))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request, data=_edit(session, sku_id, accounts, principal, request, payload, "market")
    )


@router.post(
    "/workflows/{sku_id}/purchase-request",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def request_purchase(
    request: Request,
    sku_id: UUID,
    payload: PurchaseWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(REQUEST))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request, data=_edit(session, sku_id, accounts, principal, request, payload, "request")
    )


@router.post(
    "/workflows/{sku_id}/purchase-decision",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def decide_purchase(
    request: Request,
    sku_id: UUID,
    payload: DecisionWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(APPROVE))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request, data=_edit(session, sku_id, accounts, principal, request, payload, "decision")
    )


@router.post(
    "/workflows/{sku_id}/verified-dates",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def verify_launch_dates(
    request: Request,
    sku_id: UUID,
    payload: LaunchDateWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(REVIEW))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request, data=_edit(session, sku_id, accounts, principal, request, payload, "verify_dates")
    )


@router.post(
    "/workflows/{sku_id}/review",
    response_model=SuccessEnvelope[dict[str, Any], None],
)
def review_launch(
    request: Request,
    sku_id: UUID,
    payload: ReviewWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(REVIEW))],
    accounts: account_scope,
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request, data=_edit(session, sku_id, accounts, principal, request, payload, "review")
    )


@router.get("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def read_rules(
    request: Request,
    session: db_session,
    _: view_principal,
) -> SuccessEnvelope[dict[str, Any], None]:
    row = (
        session.execute(
            text("""
        SELECT version, rule_json, actor, reason, created_at
        FROM product_new_rule_versions ORDER BY version DESC LIMIT 1
    """)
        )
        .mappings()
        .first()
    )
    return success_response(request, data=dict(row) if row else {"version": 0, "rule_json": None})


@router.put("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def write_rules(
    request: Request,
    payload: RuleWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission(CONFIGURE))],
) -> SuccessEnvelope[dict[str, Any], None]:
    session.execute(text("SELECT pg_advisory_xact_lock(92114470)"))
    version = int(
        session.execute(
            text("""
        SELECT COALESCE(MAX(version), 0) FROM product_new_rule_versions
    """)
        ).scalar_one()
    )
    if version != payload.expected_version:
        _block(409)
    new_version = version + 1
    rules = payload.model_dump(exclude={"reason", "expected_version"})
    session.execute(
        text("""
        INSERT INTO product_new_rule_versions (version, rule_json, actor, reason)
        VALUES (:version, CAST(:rule_json AS jsonb), :actor, :reason)
    """),
        {
            "version": new_version,
            "rule_json": json.dumps(rules),
            "actor": principal.user_id,
            "reason": payload.reason.strip(),
        },
    )
    session.commit()
    return success_response(request, data={"version": new_version, "rule_json": rules})
