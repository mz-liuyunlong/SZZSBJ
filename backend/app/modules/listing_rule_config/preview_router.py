"""Explicitly gated read-only Listing evidence preview."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.listing_rule_config.evaluation import rating_cutoff_la
from app.modules.listing_rule_config.models import (
    ListingEvaluationManualRequest,
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeFollowUpTask,
)
from app.modules.listing_rule_config.preview import (
    ListingEvaluationPreview,
    ListingEvaluationPreviewService,
)
from app.modules.listing_rule_config.publish import ListingEvaluationPublisher
from app.modules.listing_rule_config.tasks import account_scope_hash, manual_diagnostic

router = APIRouter(prefix="/api/listings", tags=["Listing Evaluation Preview"])
DB = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view = Depends(require_permission("page:products:listing-management:view"))
follow_up_writer = Annotated[
    Principal, Depends(require_permission("action:products:listing-management:manage-followups"))
]
manual_calculator = Annotated[
    Principal, Depends(require_permission("action:products:listing-management:calculate-all"))
]
reverter = Annotated[
    Principal, Depends(require_permission("action:products:listing-management:revert-evaluation"))
]


class ManualEvaluationRequest(BaseModel):
    confirmation: Literal["CONFIRM_LISTING_CALCULATE_ALL"]


class ManualEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_date_cn: date
    cutoff_date_la: date
    status: str
    run_id: UUID | None
    error_code: str | None


class EvaluationRevertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=5, max_length=500)
    confirmation: Literal["CONFIRM_LISTING_EVALUATION_REVERT"]


class EvaluationRevertRead(BaseModel):
    snapshot_id: UUID
    listing_id: UUID
    publication_status: str
    reverted_at: datetime
    reverted_by: str


@router.post(
    "/evaluation-snapshots/{snapshot_id}/revert",
    response_model=SuccessEnvelope[EvaluationRevertRead, dict[str, str]],
    responses={
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
def revert_evaluation_snapshot(
    request: Request,
    snapshot_id: UUID,
    payload: EvaluationRevertRequest,
    session: DB,
    account_refs: scope,
    principal: reverter,
):
    if not get_settings().listing_evaluation_publish_enabled:
        raise ApiError(code="LISTING_EVALUATION_PUBLICATION_DISABLED", status_code=503)
    snapshot = ListingEvaluationPublisher(session).revert_snapshot(
        snapshot_id=snapshot_id,
        actor=principal.user_id,
        reason=payload.reason,
        account_refs=account_refs,
    )
    return success_response(
        request,
        data=EvaluationRevertRead(
            snapshot_id=snapshot.id,
            listing_id=snapshot.listing_id,
            publication_status=snapshot.publication_status,
            reverted_at=snapshot.reverted_at,
            reverted_by=snapshot.reverted_by,
        ),
        meta={"source": "audited_publication_revert"},
    )


@router.post(
    "/evaluation-runs/manual",
    status_code=202,
    response_model=SuccessEnvelope[ManualEvaluationRead, dict[str, str]],
    responses={
        403: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
def request_manual_evaluation(
    request: Request,
    _payload: ManualEvaluationRequest,
    session: DB,
    account_refs: scope,
    principal: manual_calculator,
):
    """Queue one all-account diagnostic without publishing any Listing values."""
    if not get_settings().listing_evaluation_manual_enabled:
        raise ApiError(code="LISTING_EVALUATION_MANUAL_DISABLED", status_code=503)
    accounts = set(
        session.scalars(select(ListingManagementCurrentMart.source_account_ref).distinct()).all()
    )
    if not accounts or not accounts.issubset(account_refs):
        raise ApiError(code="LISTING_EVALUATION_ALL_SCOPE_REQUIRED", status_code=403)
    now = datetime.now(UTC)
    schedule_date_cn = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    active = session.scalar(
        select(ListingEvaluationManualRequest.id)
        .where(
            ListingEvaluationManualRequest.status.in_(("queued", "running")),
            ListingEvaluationManualRequest.schedule_date_cn == schedule_date_cn,
        )
        .limit(1)
    )
    if active is not None:
        raise ApiError(code="LISTING_EVALUATION_ALREADY_QUEUED", status_code=409)
    row = ListingEvaluationManualRequest(
        requested_by=principal.user_id,
        requested_at=now,
        schedule_date_cn=schedule_date_cn,
        cutoff_date_la=rating_cutoff_la(now),
        account_scope_hash=account_scope_hash(accounts),
        status="queued",
    )
    session.add(row)
    session.commit()
    try:
        manual_diagnostic.apply_async(args=[str(row.id)])
    except Exception:
        row.status = "failed"
        row.error_code = "LISTING_EVALUATION_QUEUE_UNAVAILABLE"
        row.finished_at = datetime.now(UTC)
        session.commit()
        raise ApiError(code="LISTING_EVALUATION_QUEUE_UNAVAILABLE", status_code=503) from None
    return success_response(
        request,
        data=ManualEvaluationRead.model_validate(row),
        meta={"source": "manual_diagnostic_request"},
    )


@router.get(
    "/evaluation-runs/manual",
    response_model=SuccessEnvelope[list[ManualEvaluationRead], dict[str, str]],
)
def list_manual_evaluation_requests(
    request: Request,
    session: DB,
    principal: manual_calculator,
):
    rows = session.scalars(
        select(ListingEvaluationManualRequest)
        .where(ListingEvaluationManualRequest.requested_by == principal.user_id)
        .order_by(ListingEvaluationManualRequest.requested_at.desc())
        .limit(20)
    ).all()
    return success_response(
        request,
        data=[ManualEvaluationRead.model_validate(row) for row in rows],
        meta={"source": "manual_diagnostic_requests"},
    )


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
    published_count: int = 0
    attempt_count: int | None
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class ListingEvaluationRunList(BaseModel):
    items: list[ListingEvaluationRunItem]
    total: int


class ListingEvaluationSnapshotItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    store_id: str
    item_id: str
    msku: str | None
    cutoff_date_la: date
    current_lifecycle: str | None
    current_grade: str | None
    lifecycle_candidate: str | None
    grade_candidate: str | None
    valid_short: int
    valid_medium: int
    valid_stock_days_30: int
    rule_version: int
    rule_source: str
    missing_evidence: list[str] = Field(default_factory=list)
    publication_status: str
    published: bool
    published_at: datetime | None = None
    published_by: str | None = None
    publication_error_code: str | None = None
    reverted_at: datetime | None = None


class ListingEvaluationSnapshotList(BaseModel):
    items: list[ListingEvaluationSnapshotItem]
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
    scoped_stats = {
        run_id: (
            int(total or 0),
            int(grade_count or 0),
            int(stage_count or 0),
            int(blocked or 0),
            int(published or 0),
        )
        for run_id, total, grade_count, stage_count, blocked, published in session.execute(
            select(
                ListingEvaluationSnapshot.run_id,
                func.count(),
                func.count(ListingEvaluationSnapshot.grade_candidate),
                func.count(ListingEvaluationSnapshot.lifecycle_candidate),
                func.count().filter(ListingEvaluationSnapshot.publication_status == "blocked"),
                func.count().filter(ListingEvaluationSnapshot.published.is_(True)),
            )
            .where(
                ListingEvaluationSnapshot.run_id.in_([row.id for row in rows]),
                ListingEvaluationSnapshot.source_account_ref.in_(account_refs),
            )
            .group_by(ListingEvaluationSnapshot.run_id)
        ).all()
    }
    return success_response(
        request,
        data=ListingEvaluationRunList(
            items=[
                ListingEvaluationRunItem.model_validate(row).model_copy(
                    update={
                        # The run is global. Its execution status, attempts, timing,
                        # and error can describe other accounts, so a scoped viewer
                        # only receives facts derived from visible snapshots.
                        "status": "scoped_snapshots",
                        "attempt_count": None,
                        "started_at": None,
                        "finished_at": None,
                        "error_code": None,
                        "total_listings": int(scoped_stats.get(row.id, (0, 0, 0, 0))[0]),
                        "processed_listings": int(scoped_stats.get(row.id, (0, 0, 0, 0))[0]),
                        "grade_candidate_count": int(scoped_stats.get(row.id, (0, 0, 0, 0))[1]),
                        "lifecycle_candidate_count": int(scoped_stats.get(row.id, (0, 0, 0, 0))[2]),
                        "blocked_count": int(scoped_stats.get(row.id, (0, 0, 0, 0, 0))[3]),
                        "published_count": int(scoped_stats.get(row.id, (0, 0, 0, 0, 0))[4]),
                    }
                )
                for row in rows
            ],
            total=count,
        ),
        meta={"source": "read_only_diagnostic"},
    )


@router.get(
    "/evaluation-runs/{run_id}/snapshots",
    response_model=SuccessEnvelope[ListingEvaluationSnapshotList, dict[str, str]],
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
    dependencies=[view],
)
def list_evaluation_snapshots(
    request: Request,
    run_id: UUID,
    session: DB,
    account_refs: scope,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return only this viewer's Listing results and safe evidence codes."""
    scoped = (
        ListingEvaluationSnapshot.run_id == run_id,
        ListingEvaluationSnapshot.source_account_ref.in_(account_refs),
    )
    total = session.scalar(
        select(func.count()).select_from(ListingEvaluationSnapshot).where(*scoped)
    )
    if not total:
        raise ApiError(code="LISTING_EVALUATION_RUN_NOT_FOUND", status_code=404)
    rows = session.scalars(
        select(ListingEvaluationSnapshot)
        .where(*scoped)
        .order_by(ListingEvaluationSnapshot.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return success_response(
        request,
        data=ListingEvaluationSnapshotList(
            items=[
                ListingEvaluationSnapshotItem.model_validate(row).model_copy(
                    update={"missing_evidence": list(row.evidence_json or [])}
                )
                for row in rows
            ],
            total=total,
        ),
        meta={"source": "scoped_diagnostic_snapshots"},
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


class ListingFollowUpUpdateRequest(BaseModel):
    status: Literal["in_progress", "completed", "canceled"]
    resolution_note: str | None = Field(default=None, max_length=1000)


@router.patch(
    "/evaluation-followups/{task_id}",
    response_model=SuccessEnvelope[ListingFollowUpItem, dict[str, str]],
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def update_evaluation_followup(
    request: Request,
    task_id: UUID,
    payload: ListingFollowUpUpdateRequest,
    session: DB,
    account_refs: scope,
    principal: follow_up_writer,
):
    """Update a scoped C/D task with an auditable completion note."""
    task = session.scalar(
        select(ListingGradeFollowUpTask).where(
            ListingGradeFollowUpTask.id == task_id,
            ListingGradeFollowUpTask.source_account_ref.in_(account_refs),
        )
    )
    if task is None:
        raise ApiError(code="LISTING_FOLLOWUP_NOT_FOUND", status_code=404)
    note = (payload.resolution_note or "").strip()
    if payload.status == "completed" and len(note) < 3:
        raise ApiError(
            code="LISTING_FOLLOWUP_RESOLUTION_NOTE_REQUIRED",
            status_code=422,
            message="完成C/D检查前必须填写处理说明",
        )
    task.status = payload.status
    task.resolution_note = note or None
    task.resolved_at = datetime.now(UTC) if payload.status in {"completed", "canceled"} else None
    task.resolved_by = principal.user_id if task.resolved_at is not None else None
    task.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(task)
    return success_response(
        request,
        data=ListingFollowUpItem.model_validate(task),
        meta={"source": "published_grade_followups"},
    )
