"""订单审核接口（PRP §7）。

权限（按 #347 RBAC 登记，迁移里插入）：
- 看：page:finance:order-review:view
- 录成本 / 撤销录入：action:finance:order-review:cost-entry
- 初审 / 撤销初审：action:finance:order-review:review1
- 终审 / 撤销终审：action:finance:order-review:review2
- 重算：action:finance:order-review:recalc
"""

from __future__ import annotations

from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.settlement_profit.order_review import service
from app.modules.settlement_profit.order_review.schemas import (
    CostEntryCreate,
    CostEntryRead,
    CostEntryResult,
    CostEntryRevoke,
    LineListData,
    LineListMeta,
    LookupData,
    PeriodListData,
    RecalcRequest,
    RecalcResultData,
    ReviewRequest,
    ReviewResultData,
    SortOrder,
    TransactionTypeListData,
)

READ_PERMISSION: Final = "page:finance:order-review:view"
COST_ENTRY_PERMISSION: Final = "action:finance:order-review:cost-entry"
REVIEW1_PERMISSION: Final = "action:finance:order-review:review1"
REVIEW2_PERMISSION: Final = "action:finance:order-review:review2"
RECALC_PERMISSION: Final = "action:finance:order-review:recalc"

router = APIRouter(prefix="/api/finance/order-review", tags=["Finance Order Review"])

db_session = Annotated[Session, Depends(get_db_session)]
reader = Annotated[Principal, Depends(require_permission(READ_PERMISSION))]
cost_writer = Annotated[Principal, Depends(require_permission(COST_ENTRY_PERMISSION))]
recalculator = Annotated[Principal, Depends(require_permission(RECALC_PERMISSION))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


def _api_error(exc: service.OrderReviewError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status_code, message=exc.message)


def _csv(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


@router.get(
    "/periods",
    responses=ERRORS,
    operation_id="listFinanceOrderReviewPeriods",
    summary="订单审核的期列表（店铺 × 期，含各状态行数）",
)
def get_periods(
    request: Request,
    session: db_session,
    principal: reader,
    store_ids: Annotated[list[str] | None, Query()] = None,
) -> SuccessEnvelope[PeriodListData, None]:
    del principal
    items = service.list_periods(session, store_ids=_csv(store_ids))
    return success_response(request, data=PeriodListData(items=items))


@router.get(
    "/lines",
    responses=ERRORS,
    operation_id="listFinanceOrderReviewLines",
    summary="订单行：收入 / 费用列 + 货本三项 + 成本来源 + 待审原因 + 审核状态",
)
def get_lines(
    request: Request,
    session: db_session,
    principal: reader,
    period_keys: Annotated[list[str] | None, Query()] = None,
    store_ids: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    reason: Annotated[list[str] | None, Query()] = None,
    item_ids: Annotated[list[str] | None, Query()] = None,
    skus: Annotated[list[str] | None, Query()] = None,
    mskus: Annotated[list[str] | None, Query()] = None,
    transaction_types: Annotated[list[str] | None, Query()] = None,
    line_kinds: Annotated[list[str] | None, Query()] = None,
    owner_ids: Annotated[list[str] | None, Query()] = None,
    keyword: Annotated[str | None, Query(max_length=120)] = None,
    sort_by: Annotated[str, Query(max_length=40)] = "posted_date",
    sort_order: SortOrder = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = 50,
) -> SuccessEnvelope[LineListData, LineListMeta]:
    del principal
    filters = service.LineFilters(
        period_keys=_csv(period_keys),
        store_ids=_csv(store_ids),
        statuses=_csv(status),
        reasons=_csv(reason),
        item_ids=_csv(item_ids),
        skus=_csv(skus),
        mskus=_csv(mskus),
        transaction_types=transaction_types or [],
        line_kinds=_csv(line_kinds),
        owner_ids=_csv(owner_ids),
        keyword=keyword,
    )
    try:
        items, total = service.list_lines(
            session,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(
        request,
        data=LineListData(items=items),
        meta=LineListMeta(total=total, page=page, page_size=page_size),
    )


@router.get(
    "/lookup",
    responses=ERRORS,
    operation_id="lookupFinanceOrderReviewValues",
    summary="精确搜索弹层候选（item_id / sku / msku / order_no，最多 1000）",
)
def get_lookup(
    request: Request,
    session: db_session,
    principal: reader,
    kind: Annotated[str, Query(max_length=16)],
    q: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=service.LOOKUP_LIMIT)] = 200,
) -> SuccessEnvelope[LookupData, None]:
    del principal
    try:
        data = service.lookup(session, kind=kind, q=q, limit=limit)
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.get(
    "/transaction-types",
    responses=ERRORS,
    operation_id="listFinanceOrderReviewTransactionTypes",
    summary="订单行里实际出现的交易类型清单（中文名 + 英文原名）",
)
def get_transaction_types(
    request: Request,
    session: db_session,
    principal: reader,
) -> SuccessEnvelope[TransactionTypeListData, None]:
    del principal
    return success_response(
        request, data=TransactionTypeListData(items=service.transaction_types(session))
    )


@router.post(
    "/cost-entries",
    status_code=201,
    responses=ERRORS,
    operation_id="createFinanceOrderReviewCostEntry",
    summary="录成本 / 确认（范围 = MSKU × 发货单或出库单；录入后重算受影响的期）",
)
def post_cost_entry(
    request: Request,
    session: db_session,
    principal: cost_writer,
    payload: CostEntryCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> SuccessEnvelope[CostEntryResult, None]:
    try:
        data = service.create_cost_entry(
            session,
            payload,
            actor=principal.user_id,
            actor_role=COST_ENTRY_PERMISSION,
            request_id=get_request_id(request),
            idempotency_key=idempotency_key,
        )
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.get(
    "/cost-entries/{entry_id}",
    responses=ERRORS,
    operation_id="getFinanceOrderReviewCostEntry",
    summary="一条录入记录（撤销前取版本号）",
)
def get_cost_entry(
    request: Request,
    session: db_session,
    principal: reader,
    entry_id: UUID,
) -> SuccessEnvelope[CostEntryRead, None]:
    del principal
    try:
        data = service.get_cost_entry(session, entry_id)
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/cost-entries/{entry_id}/revoke",
    responses=ERRORS,
    operation_id="revokeFinanceOrderReviewCostEntry",
    summary="撤销一条录入（受影响的订单行退回待审并重算）",
)
def post_cost_entry_revoke(
    request: Request,
    session: db_session,
    principal: cost_writer,
    entry_id: UUID,
    payload: CostEntryRevoke,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> SuccessEnvelope[CostEntryResult, None]:
    try:
        data = service.revoke_cost_entry(
            session,
            entry_id,
            payload,
            actor=principal.user_id,
            actor_role=COST_ENTRY_PERMISSION,
            request_id=get_request_id(request),
            idempotency_key=idempotency_key,
        )
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/review",
    responses=ERRORS,
    operation_id="reviewFinanceOrderReviewLines",
    summary="批量初审 / 终审 / 退回 / 撤销（≤ 500 行，≥ 20 行要 confirm_token，逐行返回结果）",
)
def post_review(
    request: Request,
    session: db_session,
    principal: reader,
    payload: ReviewRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> SuccessEnvelope[ReviewResultData, None]:
    needed = REVIEW1_PERMISSION if payload.stage == "first" else REVIEW2_PERMISSION
    if not has_permission(principal, needed):
        raise ApiError(code="FORBIDDEN", status_code=403, message="没有这一步审核的权限")
    try:
        data = service.review_lines(
            session,
            payload,
            actor=principal.user_id,
            actor_role=needed,
            request_id=get_request_id(request),
            idempotency_key=idempotency_key,
        )
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)


@router.post(
    "/recalc",
    responses=ERRORS,
    operation_id="recalcFinanceOrderReview",
    summary="重算订单行（按店铺 / 期；已结账的月跳过）",
)
def post_recalc(
    request: Request,
    session: db_session,
    principal: recalculator,
    payload: RecalcRequest,
) -> SuccessEnvelope[RecalcResultData, None]:
    del principal
    try:
        data = service.recalc(session, payload)
    except service.OrderReviewError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=data)
