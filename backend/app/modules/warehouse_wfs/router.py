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
    WfsFeeActualWrite,
    WfsFeeActualWriteResult,
    WfsFeeAlertListData,
    WfsFeeAlertMeta,
    WfsFeeAlertQuery,
    WfsFeeCaseWrite,
)
from app.modules.warehouse_wfs.service import WfsFeeAlertService

router = APIRouter(tags=["WFS-FEE-ALERT"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:read"))]
write_principal = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:write"))]
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


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
    "/api/warehouse/wfs-fee-actuals",
    response_model=SuccessEnvelope[WfsFeeActualWriteResult, None],
    responses=ERRORS,
)
def write_wfs_actual(
    request: Request,
    payload: WfsFeeActualWrite,
    session: db_session,
    _: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[WfsFeeActualWriteResult, None]:
    result = WfsFeeAlertService(session).write_actual(payload, account_refs)
    return success_response(request, data=result, meta=None)


@router.put(
    "/api/warehouse/wfs-fee-alerts/{mart_id}/case",
    response_model=SuccessEnvelope[dict[str, bool], None],
    responses=ERRORS,
)
def update_wfs_case(
    request: Request,
    mart_id: UUID,
    payload: WfsFeeCaseWrite,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[dict[str, bool], None]:
    WfsFeeAlertService(session).update_case(mart_id, payload, account_refs, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)
