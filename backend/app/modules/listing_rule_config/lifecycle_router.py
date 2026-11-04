"""Scoped manual Listing lifecycle review; production writes remain flag-gated."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.listing_rule_config.lifecycle import ListingLifecycleAdjustmentService
from app.modules.listing_rule_config.models import ListingLifecycleAdjustment
from app.modules.listing_rule_config.schemas import ListingStage

router = APIRouter(prefix="/api/listings/lifecycle-adjustments", tags=["Listing Lifecycle"])
DB = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
requester = Annotated[
    Principal, Depends(require_permission("action:products:listing-management:request-lifecycle"))
]
approver = Annotated[
    Principal, Depends(require_permission("action:products:listing-management:approve-lifecycle"))
]
viewer = Annotated[Principal, Depends(require_permission("page:products:listing-management:view"))]


class LifecycleAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: UUID
    requested_stage: ListingStage
    reason: str = Field(min_length=5, max_length=500)
    confirmation: Literal["CONFIRM_LISTING_LIFECYCLE"]


class LifecycleAdjustmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=5, max_length=500)
    confirmation: Literal["CONFIRM_LISTING_LIFECYCLE"]


class LifecycleAdjustmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    expected_stage: str | None
    requested_stage: str
    reason: str
    status: str
    requested_by: str
    requested_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None


class LifecycleAdjustmentList(BaseModel):
    items: list[LifecycleAdjustmentRead]
    total: int


ERRORS = {
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _require_local_publication_enabled() -> None:
    if not get_settings().listing_evaluation_publish_enabled:
        raise ApiError(
            code="LISTING_EVALUATION_PUBLICATION_DISABLED",
            status_code=503,
            message="Listing 正式写入尚未启用",
        )


@router.get(
    "",
    response_model=SuccessEnvelope[LifecycleAdjustmentList, dict[str, str]],
    responses=ERRORS,
)
def list_lifecycle_adjustments(
    request: Request,
    listing_id: UUID,
    session: DB,
    account_refs: scope,
    _principal: viewer,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    listing = ListingLifecycleAdjustmentService(session)._listing(listing_id, account_refs)
    condition = (
        ListingLifecycleAdjustment.listing_id == listing.id,
        ListingLifecycleAdjustment.source_account_ref == listing.source_account_ref,
    )
    rows = session.scalars(
        select(ListingLifecycleAdjustment)
        .where(*condition)
        .order_by(ListingLifecycleAdjustment.requested_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(
            select(func.count()).select_from(ListingLifecycleAdjustment).where(*condition)
        )
        or 0
    )
    return success_response(
        request,
        data=LifecycleAdjustmentList(
            items=[LifecycleAdjustmentRead.model_validate(row) for row in rows],
            total=total,
        ),
        meta={"source": "audited_adjustment"},
    )


@router.post(
    "",
    response_model=SuccessEnvelope[LifecycleAdjustmentRead, dict[str, str]],
    responses=ERRORS,
)
def request_lifecycle_adjustment(
    request: Request,
    payload: LifecycleAdjustmentRequest,
    session: DB,
    account_refs: scope,
    principal: requester,
):
    _require_local_publication_enabled()
    row = ListingLifecycleAdjustmentService(session).request(
        listing_id=payload.listing_id,
        requested_stage=payload.requested_stage,
        reason=payload.reason,
        actor=principal.user_id,
        account_refs=account_refs,
    )
    return success_response(
        request,
        data=LifecycleAdjustmentRead.model_validate(row),
        meta={"source": "audited_adjustment"},
    )


@router.post(
    "/{adjustment_id}/decision",
    response_model=SuccessEnvelope[LifecycleAdjustmentRead, dict[str, str]],
    responses=ERRORS,
)
def decide_lifecycle_adjustment(
    request: Request,
    adjustment_id: UUID,
    payload: LifecycleAdjustmentDecision,
    session: DB,
    account_refs: scope,
    principal: approver,
):
    _require_local_publication_enabled()
    row = ListingLifecycleAdjustmentService(session).decide(
        adjustment_id=adjustment_id,
        approve=payload.decision == "approved",
        note=payload.note,
        actor=principal.user_id,
        account_refs=account_refs,
    )
    return success_response(
        request,
        data=LifecycleAdjustmentRead.model_validate(row),
        meta={"source": "audited_adjustment"},
    )
