"""沃尔玛账单：每期汇总只读接口 + 「手动同步」。

权限（Rocky 2026-11-08：有权限的人都能点，由角色分配）：
- 看：page:finance:settlement-reconciliation:view（回款对账页面权限）
- 手动同步：action:finance:settlement-reconciliation:sync
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.walmart_bills.reader import MAX_ROWS, list_periods_page
from app.modules.walmart_bills.schemas import (
    WalmartBillPeriodListData,
    WalmartBillPeriodRead,
    WalmartBillSyncData,
)
from app.modules.walmart_bills.sync import (
    WalmartBillSyncNotConfiguredError,
    WalmartBillSyncUnavailableError,
    latest_walmart_bill_sync,
    start_walmart_bill_sync,
)

READ_PERMISSION: Final = "page:finance:settlement-reconciliation:view"
SYNC_PERMISSION: Final = "action:finance:settlement-reconciliation:sync"

ERR_SYNC_NOT_CONFIGURED: Final = "WALMART_BILL_SYNC_NOT_CONFIGURED"
ERR_SYNC_UNAVAILABLE: Final = "WALMART_BILL_SYNC_UNAVAILABLE"
ERR_RANGE_INVALID: Final = "WALMART_BILL_RANGE_INVALID"

router = APIRouter(prefix="/api/finance/walmart-bills", tags=["Finance Walmart Bills"])

db_session = Annotated[Session, Depends(get_db_session)]
reader = Annotated[Principal, Depends(require_permission(READ_PERMISSION))]
syncer = Annotated[Principal, Depends(require_permission(SYNC_PERMISSION))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


@router.get(
    "/periods",
    responses=ERRORS,
    operation_id="listFinanceWalmartBillPeriods",
    summary="沃尔玛账单每期汇总（店铺 × 一期），新到旧",
)
def get_periods(
    request: Request,
    session: db_session,
    principal: reader,
    store_id: Annotated[str | None, Query(pattern=r"^[0-9]{1,32}$")] = None,
    report_date_from: date | None = None,
    report_date_to: date | None = None,
) -> SuccessEnvelope[WalmartBillPeriodListData, None]:
    del principal
    if report_date_from and report_date_to and report_date_from > report_date_to:
        raise ApiError(code=ERR_RANGE_INVALID, status_code=422, message="开始日期晚于结束日期")
    rows, truncated = list_periods_page(
        session,
        store_id=store_id,
        report_date_from=report_date_from,
        report_date_to=report_date_to,
    )
    return success_response(
        request,
        data=WalmartBillPeriodListData(
            items=[WalmartBillPeriodRead.model_validate(row, from_attributes=True) for row in rows],
            limit=MAX_ROWS,
            truncated=truncated,
        ),
    )


@router.get(
    "/sync",
    responses=ERRORS,
    operation_id="getFinanceWalmartBillSync",
    summary="最近一次同步沃尔玛账单的状态",
)
def get_sync(
    request: Request,
    session: db_session,
    principal: reader,
) -> SuccessEnvelope[WalmartBillSyncData, None]:
    del principal
    return success_response(request, data=latest_walmart_bill_sync(session))


@router.post(
    "/sync",
    status_code=202,
    responses=ERRORS,
    operation_id="startFinanceWalmartBillSync",
    summary="手动同步沃尔玛账单（走任务中心的同步任务，已在跑就不重复开）",
)
def post_sync(
    request: Request,
    session: db_session,
    principal: syncer,
) -> SuccessEnvelope[WalmartBillSyncData, None]:
    try:
        data = start_walmart_bill_sync(
            session, actor=principal.user_id, request_id=get_request_id(request)
        )
    except WalmartBillSyncNotConfiguredError as exc:
        raise ApiError(
            code=ERR_SYNC_NOT_CONFIGURED,
            status_code=409,
            message="沃尔玛账单同步任务还没打开",
        ) from exc
    except WalmartBillSyncUnavailableError as exc:
        raise ApiError(
            code=ERR_SYNC_UNAVAILABLE,
            status_code=503,
            message="任务队列暂时不可用，请稍后再试",
        ) from exc
    return success_response(request, data=data)
