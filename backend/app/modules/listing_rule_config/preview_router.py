"""Explicitly gated read-only Listing evidence preview."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.config import get_settings
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.listing_rule_config.evaluation import rating_cutoff_la
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeFollowUpTask,
)
from app.modules.listing_rule_config.preview import (
    ListingEvaluationPreview,
    ListingEvaluationPreviewService,
)

router = APIRouter(prefix="/api/listings", tags=["Listing Evaluation Preview"])
DB = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view = Depends(require_permission("page:products:listing-management:view"))


@router.get(
    "/evaluation-preview",
    response_model=SuccessEnvelope[ListingEvaluationPreview, dict[str, str]],
    responses={
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
    dependencies=[view],
)
def get_evaluation_preview(
    request: Request,
    session: DB,
    account_refs: scope,
    listing_id: UUID,
    cutoff_la: Annotated[date | None, Query()] = None,
):
    """Never run against a production DB without a separately enabled flag."""
    if not get_settings().listing_evaluation_preview_enabled:
        raise ApiError(
            code="LISTING_EVALUATION_PREVIEW_DISABLED",
            status_code=503,
            message="真实数据试算尚未授权启用",
        )
    latest = rating_cutoff_la(datetime.now(UTC))
    cutoff = cutoff_la or latest
    if cutoff > latest or cutoff < latest - timedelta(days=45):
        raise ApiError(
            code="LISTING_EVALUATION_CUTOFF_OUT_OF_RANGE",
            status_code=422,
            message="仅允许查询最近45天以内的已结束LA业务日期",
        )
    data = ListingEvaluationPreviewService(session).evaluate(
        listing_id=listing_id, account_refs=account_refs, cutoff=cutoff
    )
    return success_response(request, data=data, meta={"source": "read_only_diagnostic"})


class ListingEvaluationBatchRequest(BaseModel):
    """Bound the diagnostic batch to avoid accidental production-size fan-out."""

    listing_ids: list[UUID] = Field(min_length=1, max_length=50)
    cutoff_la: date | None = None


class ListingEvaluationBatchData(BaseModel):
    items: list[ListingEvaluationPreview]
    total: int


@router.post(
    "/evaluation-preview/batch",
    response_model=SuccessEnvelope[ListingEvaluationBatchData, dict[str, str]],
    responses={
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
    dependencies=[view],
)
def get_evaluation_preview_batch(
    request: Request,
    payload: ListingEvaluationBatchRequest,
    session: DB,
    account_refs: scope,
):
    """Read only; fail the whole request if any ID is absent or out of scope."""
    if not get_settings().listing_evaluation_preview_enabled:
        raise ApiError(
            code="LISTING_EVALUATION_PREVIEW_DISABLED",
            status_code=503,
            message="真实数据试算尚未授权启用",
        )
    latest = rating_cutoff_la(datetime.now(UTC))
    cutoff = payload.cutoff_la or latest
    if cutoff > latest or cutoff < latest - timedelta(days=45):
        raise ApiError(
            code="LISTING_EVALUATION_CUTOFF_OUT_OF_RANGE",
            status_code=422,
            message="仅允许查询最近45天以内的已结束LA业务日期",
        )
    if len(set(payload.listing_ids)) != len(payload.listing_ids):
        raise ApiError(
            code="LISTING_EVALUATION_DUPLICATE_IDS",
            status_code=422,
            message="批量试算不能包含重复Listing",
        )
    evaluator = ListingEvaluationPreviewService(session)
    items = [
        evaluator.evaluate(listing_id=listing_id, account_refs=account_refs, cutoff=cutoff)
        for listing_id in payload.listing_ids
    ]
    return success_response(
        request,
        data=ListingEvaluationBatchData(items=items, total=len(items)),
        meta={"source": "read_only_diagnostic"},
    )


class ListingEvaluationRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_date_cn: date
    cutoff_date_la: date
    status: str
    rule_version: int
    total_listings: int
    processed_listings: int
    grade_candidate_count: int
    lifecycle_candidate_count: int
    blocked_count: int
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class ListingEvaluationRunList(BaseModel):
    items: list[ListingEvaluationRunItem]
    total: int


class ListingFollowUpItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    snapshot_id: UUID
    listing_id: UUID
    store_id: str
    item_id: str
    msku: str | None
    grade: str
    cutoff_date_la: date
    due_date_cn: date
    owner_ref: str | None
    status: str
    resolved_at: datetime | None
    resolution_note: str | None


class ListingFollowUpList(BaseModel):
    items: list[ListingFollowUpItem]
    total: int


@router.get(
    "/evaluation-runs",
    response_model=SuccessEnvelope[ListingEvaluationRunList, dict[str, str]],
    dependencies=[view],
)
def list_evaluation_runs(
    request: Request,
    session: DB,
    account_refs: scope,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    scoped = exists(
        select(ListingEvaluationSnapshot.id).where(
            ListingEvaluationSnapshot.run_id == ListingEvaluationRun.id,
            ListingEvaluationSnapshot.source_account_ref.in_(account_refs),
        )
    )
    rows = list(
        session.scalars(
            select(ListingEvaluationRun)
            .where(scoped)
            .order_by(ListingEvaluationRun.schedule_date_cn.desc())
            .limit(limit)
        ).all()
    )
    count = (
        session.scalar(select(func.count()).select_from(ListingEvaluationRun).where(scoped)) or 0
    )
    return success_response(
        request,
        data=ListingEvaluationRunList(
            items=[ListingEvaluationRunItem.model_validate(row) for row in rows],
            total=count,
        ),
        meta={"source": "read_only_diagnostic"},
    )


@router.get(
    "/evaluation-followups",
    response_model=SuccessEnvelope[ListingFollowUpList, dict[str, str]],
    dependencies=[view],
)
def list_evaluation_followups(
    request: Request,
    session: DB,
    account_refs: scope,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    rows = list(
        session.scalars(
            select(ListingGradeFollowUpTask)
            .where(ListingGradeFollowUpTask.source_account_ref.in_(account_refs))
            .order_by(
                ListingGradeFollowUpTask.due_date_cn.asc(),
                ListingGradeFollowUpTask.created_at.desc(),
            )
            .limit(limit)
        ).all()
    )
    count = (
        session.scalar(
            select(func.count())
            .select_from(ListingGradeFollowUpTask)
            .where(ListingGradeFollowUpTask.source_account_ref.in_(account_refs))
        )
        or 0
    )
    return success_response(
        request,
        data=ListingFollowUpList(
            items=[ListingFollowUpItem.model_validate(row) for row in rows],
            total=count,
        ),
        meta={"source": "published_grade_followups"},
    )
