from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

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
    SyncConfigListData,
    SyncConfigListQuery,
    SyncConfigRead,
    SyncConfigUpdate,
    SyncRunCreated,
    SyncRunListData,
    SyncRunListQuery,
    SyncRunRead,
    TriggerRequest,
    WorkItemListData,
    WorkItemListQuery,
)
from app.modules.integration_sync.service import IntegrationSyncService
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
