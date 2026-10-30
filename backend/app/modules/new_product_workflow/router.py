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
from app.core.permissions import require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

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
        reason = payload.note.strip()
        changes = {
            "purchase_review_by": principal.user_id,
            "purchase_review_at": None,
            "purchase_review_note": reason,
            "status": payload.decision,
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
        assignments = ", ".join(f"{key} = :{key}" for key in changes)
        now_fields = []
        if isinstance(payload, DecisionWrite):
            now_fields.append("purchase_review_at = now()")
        if isinstance(payload, ReviewWrite):
            now_fields.append("reviewed_at = now()")
        clause = ", ".join(
            [assignments, *now_fields, "row_version = row_version + 1", "updated_at = now()"]
        )
        session.execute(
            text(f"UPDATE product_new_workflows SET {clause} WHERE id = :id"),
            {"id": before["id"], **changes},
        )
        after = _state(session, sku_id, lock=False)

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
               identity.source_account_ref, p.product_name, p.category,
               workflow.id AS workflow_id, workflow.status,
               workflow.row_version, workflow.market_score, workflow.market_reason,
               workflow.purchase_request_qty, workflow.purchase_reason,
               workflow.purchase_review_by, workflow.purchase_review_at,
               workflow.review_result, workflow.review_reason,
               workflow.review_due_at, workflow.reviewed_by, workflow.reviewed_at
        FROM dwd_lingxing_sku_identity_index AS identity
        LEFT JOIN products AS p ON p.id = identity.product_id AND p.deleted_at IS NULL
        LEFT JOIN product_new_workflows AS workflow ON workflow.sku_identity_id = identity.id
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
