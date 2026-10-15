from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.warehouse_wfs.schemas import (
    WfsFeeAlertListData,
    WfsFeeAlertMeta,
    WfsFeeAlertQuery,
    WfsFeeArchiveRequestWrite,
    WfsFeeArchiveReviewWrite,
    WfsFeeCaseFollowWrite,
    WfsFeeCaseListData,
    WfsFeeCaseMeta,
    WfsFeeCaseQuery,
    WfsFeeCaseRead,
    WfsFeeCaseWrite,
    WfsFeeLegacyCompareResult,
    WfsFeeLegacySyncResult,
    WfsFeeRecoveredWrite,
)
from app.modules.warehouse_wfs.service import WfsFeeAlertService

router = APIRouter(tags=["WFS-FEE-CASE"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:read"))]
write_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:write"))]
review_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:review"))]
recover_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:recover"))]
sync_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:sync"))]
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


@router.get(
    "/api/warehouse/wfs-fee-cases",
    response_model=SuccessEnvelope[WfsFeeCaseListData, WfsFeeCaseMeta],
    responses=ERRORS,
)
def list_wfs_fee_cases(
    request: Request,
    query: Annotated[WfsFeeCaseQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[WfsFeeCaseListData, WfsFeeCaseMeta]:
    data, total = WfsFeeAlertService(session).list_cases(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=WfsFeeCaseMeta(page=query.page, page_size=query.page_size, total=total),
    )


@router.get(
    "/api/warehouse/wfs-fee-alerts",
    response_model=SuccessEnvelope[WfsFeeAlertListData, WfsFeeAlertMeta],
    responses=ERRORS,
)
def list_wfs_fee_alerts(
    request: Request,
    query: Annotated[WfsFeeAlertQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[WfsFeeAlertListData, WfsFeeAlertMeta]:
    data, total = WfsFeeAlertService(session).list_alerts(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=WfsFeeAlertMeta(page=query.page, page_size=query.page_size, total=total),
    )


@router.post(
    "/api/warehouse/wfs-fee-cases/sync-legacy-preview",
    response_model=SuccessEnvelope[WfsFeeLegacySyncResult, None],
    responses=ERRORS,
)
def preview_sync_legacy_wfs_fee_cases(
    request: Request,
    session: db_session,
    _: sync_principal,
) -> SuccessEnvelope[WfsFeeLegacySyncResult, None]:
    result = WfsFeeAlertService(session).sync_legacy_cases(execute=False)
    return success_response(request, data=result, meta=None)


@router.post(
    "/api/warehouse/wfs-fee-cases/sync-legacy-execute",
    response_model=SuccessEnvelope[WfsFeeLegacySyncResult, None],
    responses=ERRORS,
)
def execute_sync_legacy_wfs_fee_cases(
    request: Request,
    session: db_session,
    _: sync_principal,
) -> SuccessEnvelope[WfsFeeLegacySyncResult, None]:
    result = WfsFeeAlertService(session).sync_legacy_cases(execute=True)
    return success_response(request, data=result, meta=None)


@router.get(
    "/api/warehouse/wfs-fee-cases/legacy-compare",
    response_model=SuccessEnvelope[WfsFeeLegacyCompareResult, None],
    responses=ERRORS,
)
def compare_legacy_wfs_fee_cases(
    request: Request,
    session: db_session,
    _: sync_principal,
) -> SuccessEnvelope[WfsFeeLegacyCompareResult, None]:
    result = WfsFeeAlertService(session).compare_legacy_cases()
    return success_response(request, data=result, meta=None)


@router.get(
    "/api/warehouse/wfs-fee-cases/{case_id}",
    response_model=SuccessEnvelope[WfsFeeCaseRead, None],
    responses=ERRORS,
)
def get_wfs_fee_case(
    request: Request,
    case_id: UUID,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[WfsFeeCaseRead, None]:
    data = WfsFeeAlertService(session).get_case(case_id, account_refs)
    return success_response(request, data=data, meta=None)


@router.put(
    "/api/warehouse/wfs-fee-alerts/{case_id}/case",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def update_wfs_case_compat(
    request: Request,
    case_id: UUID,
    payload: WfsFeeCaseWrite,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).update_case(case_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)


@router.post(
    "/api/warehouse/wfs-fee-cases/{case_id}/follow",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def save_wfs_fee_case_follow(
    request: Request,
    case_id: UUID,
    payload: WfsFeeCaseFollowWrite,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).save_follow(case_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)


@router.post(
    "/api/warehouse/wfs-fee-cases/{case_id}/archive-request",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def request_wfs_fee_case_archive(
    request: Request,
    case_id: UUID,
    payload: WfsFeeArchiveRequestWrite,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).request_archive(case_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)


@router.post(
    "/api/warehouse/wfs-fee-cases/{case_id}/archive-review",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def review_wfs_fee_case_archive(
    request: Request,
    case_id: UUID,
    payload: WfsFeeArchiveReviewWrite,
    session: db_session,
    principal: review_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).review_archive(case_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)


@router.post(
    "/api/warehouse/wfs-fee-cases/{case_id}/mark-recovered",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def mark_wfs_fee_case_recovered(
    request: Request,
    case_id: UUID,
    payload: WfsFeeRecoveredWrite,
    session: db_session,
    principal: recover_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).mark_recovered(case_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)
