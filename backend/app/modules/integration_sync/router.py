from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.integration_sync.schemas import (
    BackfillRequest,
    InterfaceListData,
    InterfaceListQuery,
    PageQuery,
    RawRequestMetadataListData,
    ReadMeta,
    RefundMartPendingData,
    SyncConfigListData,
    SyncConfigListQuery,
    SyncConfigRead,
    SyncConfigUpdate,
    SyncRunCreated,
    SyncRunListData,
    SyncRunListQuery,
    SyncRunRead,
    SyncTaskDashboardData,
    TriggerRequest,
    WorkItemListData,
    WorkItemListQuery,
)
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.models import IntegrationSyncAnomaly, IntegrationSyncAnomalyAudit
from app.modules.integration_sync.tasks import TaskDispatchError, dispatch_sync_run

router = APIRouter(prefix="/api/integrations", tags=["Integration Sync Governance"])

db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("integrations:read"))]
update_principal = Annotated[Principal, Depends(require_permission("integrations:update"))]
execute_principal = Annotated[Principal, Depends(require_permission("integrations:execute"))]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **READ_ERRORS,
    409: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _meta(
    *objects: str,
    freshness_at: datetime | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> ReadMeta:
    return ReadMeta(
        source_objects=list(objects),
        freshness_at=freshness_at,
        page=page,
        page_size=page_size,
        total=total,
    )


def _latest(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present, default=None)


@router.get(
    "/interfaces",
    response_model=SuccessEnvelope[InterfaceListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationInterfaces",
)
def list_interfaces(
    request: Request,
    query: Annotated[InterfaceListQuery, Query()],
    session: db_session,
    _: read_principal,
) -> SuccessEnvelope[InterfaceListData, ReadMeta]:
    data, total = IntegrationSyncService(session).list_interfaces(query)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_interfaces",
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


def _dispatch(run_id: UUID) -> None:
    try:
        dispatch_sync_run(run_id)
    except TaskDispatchError:
        from app.core.api import ApiError

        raise ApiError(code="TASK_DISPATCH_UNAVAILABLE", status_code=503) from None


@router.get(
    "/sync-configs",
    response_model=SuccessEnvelope[SyncConfigListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncConfigs",
)
def list_sync_configs(
    request: Request,
    query: Annotated[SyncConfigListQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncConfigListData, ReadMeta]:
    data, total = IntegrationSyncService(session).list_configs(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_sync_configs",
            freshness_at=_latest(*(item.updated_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.patch(
    "/sync-configs/{config_id}",
    response_model=SuccessEnvelope[SyncConfigRead, ReadMeta],
    responses=WRITE_ERRORS,
    operation_id="updateIntegrationSyncConfig",
)
def update_sync_config(
    request: Request,
    config_id: UUID,
    payload: SyncConfigUpdate,
    session: db_session,
    principal: update_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncConfigRead, ReadMeta]:
    data = IntegrationSyncService(session).update_config(
        config_id,
        payload,
        account_refs,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
    )
    return success_response(
        request,
        data=data,
        meta=_meta("gov_integration_sync_configs", freshness_at=data.updated_at),
    )


@router.post(
    "/sync-configs/{config_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[SyncRunCreated, ReadMeta],
    responses=WRITE_ERRORS,
    operation_id="createManualIntegrationSyncRun",
)
def create_manual_run(
    request: Request,
    config_id: UUID,
    payload: TriggerRequest,
    session: db_session,
    principal: execute_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncRunCreated, ReadMeta]:
    data = IntegrationSyncService(session).create_manual_run(
        config_id,
        payload,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
        account_refs=account_refs,
    )
    _dispatch(data.run_id)
    return success_response(request, data=data, meta=_meta("gov_integration_sync_runs"))


@router.post(
    "/sync-runs/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[SyncRunCreated, ReadMeta],
    responses=WRITE_ERRORS,
    operation_id="retryIntegrationSyncRun",
)
def retry_run(
    request: Request,
    run_id: UUID,
    payload: TriggerRequest,
    session: db_session,
    principal: execute_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncRunCreated, ReadMeta]:
    data = IntegrationSyncService(session).create_retry_run(
        run_id,
        payload,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
        account_refs=account_refs,
    )
    _dispatch(data.run_id)
    return success_response(request, data=data, meta=_meta("gov_integration_sync_runs"))


@router.post(
    "/sync-configs/{config_id}/backfill",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[SyncRunCreated, ReadMeta],
    responses=WRITE_ERRORS,
    operation_id="createIntegrationSyncBackfill",
)
def create_backfill_run(
    request: Request,
    config_id: UUID,
    payload: BackfillRequest,
    session: db_session,
    principal: execute_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncRunCreated, ReadMeta]:
    data = IntegrationSyncService(session).create_backfill_run(
        config_id,
        payload,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
        account_refs=account_refs,
    )
    _dispatch(data.run_id)
    return success_response(request, data=data, meta=_meta("gov_integration_sync_runs"))


@router.get(
    "/sync-tasks/refund-mart-pending",
    response_model=SuccessEnvelope[RefundMartPendingData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listRefundMartPendingDays",
)
def list_refund_mart_pending(
    request: Request,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[RefundMartPendingData, ReadMeta]:
    data = IntegrationSyncService(session).refund_mart_pending_days(account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta("gov_integration_sync_run_events", "gov_integration_sync_runs"),
    )


@router.get(
    "/sync-tasks/dashboard",
    response_model=SuccessEnvelope[SyncTaskDashboardData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="getIntegrationSyncDashboard",
)
def get_sync_dashboard(
    request: Request,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncTaskDashboardData, ReadMeta]:
    data = IntegrationSyncService(session).task_dashboard(account_refs)
    return success_response(request, data=data, meta=_meta("gov_integration_sync_runs"))


@router.get(
    "/sync-runs",
    response_model=SuccessEnvelope[SyncRunListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncRuns",
)
def list_sync_runs(
    request: Request,
    query: Annotated[SyncRunListQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncRunListData, ReadMeta]:
    data, total = IntegrationSyncService(session).list_runs(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_sync_runs",
            freshness_at=_latest(*(item.created_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/sync-runs/{run_id}",
    response_model=SuccessEnvelope[SyncRunRead, ReadMeta],
    responses=READ_ERRORS,
    operation_id="getIntegrationSyncRun",
)
def get_sync_run(
    request: Request,
    run_id: UUID,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncRunRead, ReadMeta]:
    data = IntegrationSyncService(session).get_run(run_id, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_sync_runs",
            freshness_at=_latest(
                data.finished_at,
                data.started_at,
                data.queued_at,
                data.created_at,
            ),
        ),
    )


@router.get(
    "/sync-runs/{run_id}/work-items",
    response_model=SuccessEnvelope[WorkItemListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncRunWorkItems",
)
def list_work_items(
    request: Request,
    run_id: UUID,
    query: Annotated[WorkItemListQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[WorkItemListData, ReadMeta]:
    data, total = IntegrationSyncService(session).list_work_items(run_id, query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_sync_run_work_items",
            freshness_at=_latest(
                *(item.finished_at or item.started_at or item.created_at for item in data.items)
            ),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/sync-runs/{run_id}/raw-request-refs",
    response_model=SuccessEnvelope[RawRequestMetadataListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncRunRawRequestRefs",
)
def list_raw_request_refs(
    request: Request,
    run_id: UUID,
    query: Annotated[PageQuery, Query()],
    session: db_session,
    _: Annotated[Principal, Depends(require_permission("integrations:raw_metadata:read"))],
    account_refs: source_scope,
) -> SuccessEnvelope[RawRequestMetadataListData, ReadMeta]:
    data, total = IntegrationSyncService(session).list_raw_request_refs(
        run_id,
        page=query.page,
        page_size=query.page_size,
        account_refs=account_refs,
    )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "ods_api_raw_request_refs",
            "ods_api_raw_blobs",
            freshness_at=_latest(*(item.received_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


class SyncAnomalyRead(BaseModel):
    id: UUID
    run_id: UUID
    source_account_ref: str
    interface_key: str
    business_date: date
    error_code: str
    store_id: str | None
    item_id: str | None
    msku: str | None
    local_sku: str | None
    platform_order_no: str | None
    campaign_name: str | None
    status: str
    details: dict[str, object]
    occurrence_count: int
    owner_note: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class SyncAnomalyListData(BaseModel):
    items: list[SyncAnomalyRead]


class SyncAnomalyResolution(BaseModel):
    status: str
    note: str = Field(min_length=3, max_length=1000)


@router.get(
    "/sync-anomalies",
    response_model=SuccessEnvelope[SyncAnomalyListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncAnomalies",
)
def list_sync_anomalies(
    request: Request,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    interface_key: str | None = None,
    business_date: date | None = None,
) -> SuccessEnvelope[SyncAnomalyListData, ReadMeta]:
    predicate = [IntegrationSyncAnomaly.source_account_ref.in_(account_refs)]
    if status_filter:
        predicate.append(IntegrationSyncAnomaly.status == status_filter)
    if interface_key:
        predicate.append(IntegrationSyncAnomaly.interface_key == interface_key)
    if business_date:
        predicate.append(IntegrationSyncAnomaly.business_date == business_date)
    total = session.scalar(select(func.count()).select_from(IntegrationSyncAnomaly).where(*predicate)) or 0
    rows = session.scalars(
        select(IntegrationSyncAnomaly).where(*predicate)
        .order_by(IntegrationSyncAnomaly.last_seen_at.desc(), IntegrationSyncAnomaly.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return success_response(
        request,
        data=SyncAnomalyListData(items=[SyncAnomalyRead.model_validate(row) for row in rows]),
        meta=_meta("gov_integration_sync_anomalies", page=page, page_size=page_size, total=total),
    )


@router.patch(
    "/sync-anomalies/{anomaly_id}",
    response_model=SuccessEnvelope[SyncAnomalyRead, ReadMeta],
    responses=WRITE_ERRORS,
    operation_id="updateIntegrationSyncAnomaly",
)
def update_sync_anomaly(
    request: Request,
    anomaly_id: UUID,
    payload: SyncAnomalyResolution,
    session: db_session,
    principal: update_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncAnomalyRead, ReadMeta]:
    from app.core.api import ApiError

    if payload.status not in {
        "pending", "investigating", "fix_pending", "review_pending",
        "resolved", "dismissed",
    }:
        raise ApiError(code="SYNC_ANOMALY_STATUS_INVALID", status_code=422)
    row = session.scalar(
        select(IntegrationSyncAnomaly)
        .where(
            IntegrationSyncAnomaly.id == anomaly_id,
            IntegrationSyncAnomaly.source_account_ref.in_(account_refs),
        ).with_for_update()
    )
    if row is None:
        raise ApiError(code="SYNC_ANOMALY_NOT_FOUND", status_code=404)
    previous_status = row.status
    session.add(IntegrationSyncAnomalyAudit(
        id=uuid4(),
        anomaly_id=row.id,
        actor_ref=principal.user_id,
        from_status=previous_status,
        to_status=payload.status,
        note=payload.note,
    ))
    row.status = payload.status
    row.owner_note = payload.note
    row.updated_by = principal.user_id
    row.resolved_at = datetime.now(UTC) if payload.status in {"resolved", "dismissed"} else None
    session.commit()
    session.refresh(row)
    return success_response(
        request,
        data=SyncAnomalyRead.model_validate(row),
        meta=_meta("gov_integration_sync_anomalies", freshness_at=row.last_seen_at),
    )


class SyncAnomalyAuditRead(BaseModel):
    id: UUID
    anomaly_id: UUID
    actor_ref: str
    from_status: str
    to_status: str
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncAnomalyAuditListData(BaseModel):
    items: list[SyncAnomalyAuditRead]


@router.get(
    "/sync-anomalies/{anomaly_id}/history",
    response_model=SuccessEnvelope[SyncAnomalyAuditListData, ReadMeta],
    responses=READ_ERRORS,
    operation_id="listIntegrationSyncAnomalyHistory",
)
def list_sync_anomaly_history(
    request: Request,
    anomaly_id: UUID,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SyncAnomalyAuditListData, ReadMeta]:
    from app.core.api import ApiError

    valid = session.scalar(
        select(IntegrationSyncAnomaly.id).where(
            IntegrationSyncAnomaly.id == anomaly_id,
            IntegrationSyncAnomaly.source_account_ref.in_(account_refs),
        )
    )
    if valid is None:
        raise ApiError(code="SYNC_ANOMALY_NOT_FOUND", status_code=404)
    rows = session.scalars(
        select(IntegrationSyncAnomalyAudit)
        .where(IntegrationSyncAnomalyAudit.anomaly_id == anomaly_id)
        .order_by(IntegrationSyncAnomalyAudit.created_at.desc())
        .limit(200)
    ).all()
    return success_response(
        request,
        data=SyncAnomalyAuditListData(
            items=[SyncAnomalyAuditRead.model_validate(row) for row in rows]
        ),
        meta=_meta("gov_integration_sync_anomaly_audit"),
    )
