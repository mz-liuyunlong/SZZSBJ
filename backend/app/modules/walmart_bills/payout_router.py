"""回款对账（PR-2）接口。

权限（Rocky 2026-11-10）：
- 看：page:finance:settlement-reconciliation:view
- 初审（确认到账）、自动配对、手动配对 / 撤销：action:finance:settlement-reconciliation:review1
- 终审通过 / 驳回、收款账户映射维护：action:finance:settlement-reconciliation:review2
- 打款异常跟进：action:finance:settlement-reconciliation:follow
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import (
    ApiError,
    ErrorCode,
    ErrorEnvelope,
    SuccessEnvelope,
    get_request_id,
    success_response,
)
from app.core.auth import Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.walmart_bills.payout_schemas import (
    PayoutAccountCreateRequest,
    PayoutAccountListData,
    PayoutAccountRead,
    PayoutAccountUpdateRequest,
    PayoutAutoMatchData,
    PayoutFollowRead,
    PayoutFollowRequest,
    PayoutLineListData,
    PayoutManualMatchRequest,
    PayoutMatchData,
    PayoutPeriodDetailData,
    PayoutPeriodListData,
    PayoutReviewData,
    PayoutReviewRequest,
    PayoutUnmatchRequest,
)
from app.modules.walmart_bills.payout_service import PayoutReconError, PayoutReconService

READ_PERMISSION: Final = "page:finance:settlement-reconciliation:view"
REVIEW1_PERMISSION: Final = "action:finance:settlement-reconciliation:review1"
REVIEW2_PERMISSION: Final = "action:finance:settlement-reconciliation:review2"
FOLLOW_PERMISSION: Final = "action:finance:settlement-reconciliation:follow"
ERR_RANGE_INVALID: Final = "PAYOUT_RECON_RANGE_INVALID"

router = APIRouter(prefix="/api/finance/payout-recon", tags=["Finance Payout Reconciliation"])

db_session = Annotated[Session, Depends(get_db_session)]
reader = Annotated[Principal, Depends(require_permission(READ_PERMISSION))]
reviewer1 = Annotated[Principal, Depends(require_permission(REVIEW1_PERMISSION))]
reviewer2 = Annotated[Principal, Depends(require_permission(REVIEW2_PERMISSION))]
follower = Annotated[Principal, Depends(require_permission(FOLLOW_PERMISSION))]
StoreId = Annotated[str | None, Query(pattern=r"^[0-9]{1,32}$")]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


def _api_error(exc: PayoutReconError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status_code, message=exc.message)


@router.get(
    "/periods",
    responses=ERRORS,
    operation_id="listFinancePayoutReconPeriods",
    summary="回款对账：每店每期应付、到账、审核、跟进（2026-10 起，新到旧）",
)
def get_periods(
    request: Request,
    session: db_session,
    principal: reader,
    store_id: StoreId = None,
    report_date_from: date | None = None,
    report_date_to: date | None = None,
) -> SuccessEnvelope[PayoutPeriodListData, None]:
    del principal
    if report_date_from and report_date_to and report_date_from > report_date_to:
        raise ApiError(code=ERR_RANGE_INVALID, status_code=422, message="开始日期晚于结束日期")
    data = PayoutReconService(session).list_periods(
        date_from=report_date_from, date_to=report_date_to, store_id=store_id
    )
    return success_response(request, data=data)


@router.get(
    "/periods/{store_id}/{report_key}",
    responses=ERRORS,
    operation_id="getFinancePayoutReconPeriod",
    summary="回款对账：一期的详情（科目合计、配对历史、审核记录、跟进记录）",
)
def get_period(
    request: Request,
    session: db_session,
    principal: reader,
    store_id: str,
    report_key: str,
) -> SuccessEnvelope[PayoutPeriodDetailData, None]:
    del principal
    try:
        data = PayoutReconService(session).period_detail(store_id, report_key)
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.get(
    "/lines",
    responses=ERRORS,
    operation_id="listFinancePayoutReconLines",
    summary="回款对账：可手动配对的到账（映射过的收款账户里、10 月起的收入流水）",
)
def get_lines(
    request: Request,
    session: db_session,
    principal: reviewer1,
    store_id: StoreId = None,
) -> SuccessEnvelope[PayoutLineListData, None]:
    del principal
    return success_response(request, data=PayoutReconService(session).candidate_lines(store_id))


@router.post(
    "/auto-match",
    responses=ERRORS,
    operation_id="autoMatchFinancePayoutRecon",
    summary="回款对账：按规则自动配对（只配能唯一确定的）",
)
def post_auto_match(
    request: Request, session: db_session, principal: reviewer1
) -> SuccessEnvelope[PayoutAutoMatchData, None]:
    data = PayoutReconService(session).auto_match(
        actor=principal.user_id, request_id=get_request_id(request)
    )
    return success_response(request, data=data)


@router.post(
    "/matches",
    responses=ERRORS,
    operation_id="createFinancePayoutReconMatch",
    summary="回款对账：手动把一笔到账配给一期或几期（合并打款）",
)
def post_match(
    request: Request,
    session: db_session,
    principal: reviewer1,
    payload: PayoutManualMatchRequest,
) -> SuccessEnvelope[PayoutMatchData, None]:
    try:
        data = PayoutReconService(session).manual_match(
            payload, actor=principal.user_id, request_id=get_request_id(request)
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/matches/{match_id}/undo",
    responses=ERRORS,
    operation_id="undoFinancePayoutReconMatch",
    summary="回款对账：撤销一次配对（必须写原因；已初审 / 终审的不能撤）",
)
def post_unmatch(
    request: Request,
    session: db_session,
    principal: reviewer1,
    match_id: UUID,
    payload: PayoutUnmatchRequest,
) -> SuccessEnvelope[PayoutMatchData, None]:
    try:
        data = PayoutReconService(session).unmatch(
            match_id,
            reason=payload.reason,
            actor=principal.user_id,
            request_id=get_request_id(request),
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/reviews",
    responses=ERRORS,
    operation_id="reviewFinancePayoutRecon",
    summary="回款对账：批量初审 / 终审通过 / 终审驳回（不在这一步的期次跳过）",
)
def post_review(
    request: Request,
    session: db_session,
    payload: PayoutReviewRequest,
    principal: Annotated[Principal, Depends(require_permission(READ_PERMISSION))],
) -> SuccessEnvelope[PayoutReviewData, None]:
    needed = REVIEW1_PERMISSION if payload.kind == "review1_pass" else REVIEW2_PERMISSION
    if not has_permission(principal, needed):
        raise ApiError(
            code=ErrorCode.FORBIDDEN, status_code=403, details={"required_permission": needed}
        )
    try:
        data = PayoutReconService(session).review(
            payload, actor=principal.user_id, request_id=get_request_id(request)
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/follow-ups",
    responses=ERRORS,
    operation_id="createFinancePayoutReconFollowUp",
    summary="回款对账：打款异常跟进（追加一条）",
)
def post_follow(
    request: Request,
    session: db_session,
    principal: follower,
    payload: PayoutFollowRequest,
) -> SuccessEnvelope[PayoutFollowRead, None]:
    try:
        data = PayoutReconService(session).follow(
            payload, actor=principal.user_id, request_id=get_request_id(request)
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.get(
    "/accounts",
    responses=ERRORS,
    operation_id="listFinancePayoutReconAccounts",
    summary="回款对账：店铺收款账户映射（含历史）+ 可选的入账账户和店铺",
)
def get_accounts(
    request: Request, session: db_session, principal: reader
) -> SuccessEnvelope[PayoutAccountListData, None]:
    del principal
    return success_response(request, data=PayoutReconService(session).list_accounts())


@router.post(
    "/accounts",
    responses=ERRORS,
    operation_id="createFinancePayoutReconAccount",
    summary="回款对账：新增 / 更换店铺收款账户（更换要写原因，旧记录自动截止）",
)
def post_account(
    request: Request,
    session: db_session,
    principal: reviewer2,
    payload: PayoutAccountCreateRequest,
) -> SuccessEnvelope[PayoutAccountRead, None]:
    try:
        data = PayoutReconService(session).create_account(payload, actor=principal.user_id)
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.put(
    "/accounts/{account_id}",
    responses=ERRORS,
    operation_id="updateFinancePayoutReconAccount",
    summary="回款对账：改一条收款账户（入账账户、收款账户识别）",
)
def put_account(
    request: Request,
    session: db_session,
    principal: reviewer2,
    account_id: UUID,
    payload: PayoutAccountUpdateRequest,
) -> SuccessEnvelope[PayoutAccountRead, None]:
    try:
        data = PayoutReconService(session).update_account(
            account_id, payload, actor=principal.user_id
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/accounts/{account_id}/deactivate",
    responses=ERRORS,
    operation_id="deactivateFinancePayoutReconAccount",
    summary="回款对账：停用一条收款账户（写原因，留历史）",
)
def post_deactivate_account(
    request: Request,
    session: db_session,
    principal: reviewer2,
    account_id: UUID,
    payload: PayoutUnmatchRequest,
) -> SuccessEnvelope[None, None]:
    try:
        PayoutReconService(session).deactivate_account(
            account_id, reason=payload.reason, actor=principal.user_id
        )
    except PayoutReconError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=None)
