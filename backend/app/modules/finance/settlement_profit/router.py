"""HTTP routes of 结算利润 V2 (PRP §7): /api/finance/settlement-profit/*.

Reads need ``page:finance:settlement-profit:view`` plus a store data scope; writes also
need the action permission, an ``Idempotency-Key`` header and, for high-risk actions,
a typed ``confirm_token`` (``CLOSE YYYY-MM`` / ``REOPEN YYYY-MM`` / ``CONFIG YYYY-MM`` /
``REVIEW <n>`` for batch review of 20 lines or more).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.db.session import get_db_session

from ..settlement_profit_models import utc_now
from . import commands, queries
from .access import SettlementAccess, get_settlement_access
from .schemas import (
    AdjustmentCreate,
    AdjustmentResult,
    CloseRequest,
    MonthCloseResult,
    NetProfitConfigOut,
    NetProfitConfigResult,
    NetProfitConfigUpdate,
    ReopenRequest,
    ReviewRequest,
    ReviewResult,
    RevokeRequest,
    WriteMeta,
)

router = APIRouter(prefix="/api/finance/settlement-profit", tags=["Finance Settlement Profit"])

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}

Db = Annotated[Session, Depends(get_db_session)]
Access = Annotated[SettlementAccess, Depends(get_settlement_access)]
Months = Annotated[list[str] | None, Query(description="账单月 YYYY-MM，可重复")]
StoreIds = Annotated[list[str] | None, Query(description="店铺 id，可重复")]
OwnerIds = Annotated[list[str] | None, Query(description="负责人，可重复")]
PageNo = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=queries.MAX_PAGE_SIZE)]
SortOrder = Annotated[Literal["asc", "desc"], Query()]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
ReadEnvelope = SuccessEnvelope[dict[str, Any], dict[str, Any]]
ReviewReason = Literal[
    "missing_purchase", "missing_head", "unassigned", "unmapped_store", "reconcile_diff"
]


def get_recalculator() -> commands.Recalculator:
    """Overridable; the default defers until the settlement-line DB loader is on main."""
    return commands.deferred_recalculator


Recalc = Annotated[commands.Recalculator, Depends(get_recalculator)]


def _ctx(request: Request, access: SettlementAccess, endpoint: str, key: str):
    return commands.WriteContext(
        access=access,
        endpoint=endpoint,
        idempotency_key=key.strip(),
        request_id=get_request_id(request),
        now=utc_now(),
    )


def _read(request: Request, result: tuple[dict[str, Any], dict[str, Any]]) -> ReadEnvelope:
    data, meta = result
    return success_response(request, data=data, meta=meta)


# ------------------------------------------------------------------ reads


@router.get(
    "/stores",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="listSettlementProfitStores",
    summary="店铺筛选项（不含未对上店铺）",
)
def list_stores(request: Request, session: Db, access: Access, months: Months = None):
    rows = queries.list_stores(session, access, queries.parse_months(months))
    return success_response(
        request,
        data={"rows": rows},
        meta=queries.meta(["mart_settlement_reconcile_store_month"], len(rows), None, None),
    )


@router.get(
    "/summary",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="getSettlementProfitSummary",
    summary="汇总：商品 / 店铺 / 负责人视图",
)
def get_summary(
    request: Request,
    session: Db,
    access: Access,
    months: Months = None,
    store_ids: StoreIds = None,
    owner_ids: OwnerIds = None,
    view: Annotated[Literal["item", "store", "owner"], Query()] = "item",
    currency: Annotated[Literal["USD", "CNY"], Query()] = "USD",
    page: PageNo = 1,
    page_size: PageSize = 50,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: SortOrder = "desc",
):
    return _read(
        request,
        queries.summary(
            session,
            access,
            months=queries.parse_months(months),
            stores=access.requested_stores(store_ids),
            owner_ids=owner_ids,
            view=view,
            currency=currency,
            page=queries.Page.of(page, page_size),
            sort_by=sort_by,
            sort_order=sort_order,
        ),
    )


@router.get(
    "/items/{store_id}/{item_id}",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="getSettlementProfitItem",
    summary="商品按月瀑布",
)
def get_item(
    request: Request,
    session: Db,
    access: Access,
    store_id: str,
    item_id: str,
    months: Months = None,
):
    return _read(
        request,
        queries.item_detail(session, access, store_id, item_id, queries.parse_months(months)),
    )


@router.get(
    "/orders",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="listSettlementProfitOrders",
    summary="订单审核清单（含待指定、对平差额待办）",
)
def list_orders(
    request: Request,
    session: Db,
    access: Access,
    months: Months = None,
    store_ids: StoreIds = None,
    owner_ids: OwnerIds = None,
    status: Annotated[
        list[Literal["pending", "auto", "adjusted", "first_passed", "final_passed", "rejected"]]
        | None,
        Query(),
    ] = None,
    reason: Annotated[list[ReviewReason] | None, Query()] = None,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: SortOrder = "asc",
):
    return _read(
        request,
        queries.orders(
            session,
            access,
            months=queries.parse_months(months),
            stores=access.requested_stores(store_ids),
            owner_ids=owner_ids,
            status=status,
            reason=reason,
            keyword=keyword or None,
            page=queries.Page.of(page, page_size),
            sort_by=sort_by,
            sort_order=sort_order,
        ),
    )


@router.get(
    "/inventory",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="listSettlementProfitInventory",
    summary="库存异动：汇总 + 明细",
)
def list_inventory(
    request: Request,
    session: Db,
    access: Access,
    months: Months = None,
    store_ids: StoreIds = None,
    category: Annotated[
        list[Literal["loss", "non_loss", "claim", "unclassified", "lx_adjust", "unknown"]] | None,
        Query(),
    ] = None,
):
    return _read(
        request,
        queries.inventory(
            session,
            access,
            months=queries.parse_months(months),
            stores=access.requested_stores(store_ids),
            category=category,
        ),
    )


@router.get(
    "/adjustments",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="listSettlementProfitAdjustments",
    summary="调整台账",
)
def list_adjustments(
    request: Request,
    session: Db,
    access: Access,
    months: Months = None,
    status: Annotated[Literal["active", "revoked"] | None, Query()] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
):
    return _read(
        request,
        queries.adjustments(
            session,
            access,
            months=queries.parse_months(months),
            status=status,
            page=queries.Page.of(page, page_size),
        ),
    )


@router.get(
    "/reconcile",
    response_model=ReadEnvelope,
    responses=ERRORS,
    operation_id="listSettlementProfitReconcile",
    summary="店铺月对平",
)
def list_reconcile(
    request: Request, session: Db, access: Access, months: Months = None, store_ids: StoreIds = None
):
    return _read(
        request,
        queries.reconcile(
            session,
            access,
            months=queries.parse_months(months),
            stores=access.requested_stores(store_ids),
        ),
    )


@router.get(
    "/config/net-profit",
    response_model=SuccessEnvelope[NetProfitConfigOut, dict[str, Any]],
    responses=ERRORS,
    operation_id="getSettlementProfitNetProfitConfig",
    summary="纯利设置（按月生效）",
)
def get_net_profit_config(
    request: Request, session: Db, access: Access, month: Annotated[str, Query()]
):
    data = commands.get_config(session, access, month)
    return success_response(
        request,
        data=data,
        meta=queries.meta(["cfg_net_profit_allocation"], 1, None, None),
    )


# ------------------------------------------------------------------ writes


def _write(request: Request, result: dict[str, Any]):
    return success_response(request, data=result["data"], meta=commands.write_meta(result))


@router.post(
    "/orders/{line_id}/adjustments",
    response_model=SuccessEnvelope[AdjustmentResult, WriteMeta],
    responses=ERRORS,
    operation_id="createSettlementProfitAdjustment",
    summary="调整一行：成本 / 金额 / 指定商品 / 指定店铺 / 备注",
)
def create_adjustment(
    request: Request,
    session: Db,
    access: Access,
    recalc: Recalc,
    line_id: UUID,
    body: AdjustmentCreate,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "POST /orders/{line_id}/adjustments", idempotency_key)
    return _write(request, commands.create_adjustment(session, ctx, line_id, body, recalc))


@router.post(
    "/orders/review",
    response_model=SuccessEnvelope[ReviewResult, WriteMeta],
    responses=ERRORS,
    operation_id="reviewSettlementProfitOrders",
    summary="批量初审 / 终审 / 退回（≤ 500 行，逐行结果）",
)
def review_orders(
    request: Request,
    session: Db,
    access: Access,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "POST /orders/review", idempotency_key)
    return _write(request, commands.review_lines(session, ctx, body))


@router.post(
    "/adjustments/{adjustment_id}/revoke",
    response_model=SuccessEnvelope[AdjustmentResult, WriteMeta],
    responses=ERRORS,
    operation_id="revokeSettlementProfitAdjustment",
    summary="撤销调整",
)
def revoke_adjustment(
    request: Request,
    session: Db,
    access: Access,
    recalc: Recalc,
    adjustment_id: UUID,
    body: RevokeRequest,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "POST /adjustments/{adjustment_id}/revoke", idempotency_key)
    return _write(request, commands.revoke_adjustment(session, ctx, adjustment_id, body, recalc))


@router.post(
    "/months/{month}/close",
    response_model=SuccessEnvelope[MonthCloseResult, WriteMeta],
    responses=ERRORS,
    operation_id="closeSettlementProfitMonth",
    summary="结账（confirm_token = CLOSE YYYY-MM）",
)
def close_month(
    request: Request,
    session: Db,
    access: Access,
    month: str,
    body: CloseRequest,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "POST /months/{month}/close", idempotency_key)
    return _write(request, commands.close_month(session, ctx, month, body))


@router.post(
    "/months/{month}/reopen",
    response_model=SuccessEnvelope[MonthCloseResult, WriteMeta],
    responses=ERRORS,
    operation_id="reopenSettlementProfitMonth",
    summary="反结账（confirm_token = REOPEN YYYY-MM，原因必填）",
)
def reopen_month(
    request: Request,
    session: Db,
    access: Access,
    recalc: Recalc,
    month: str,
    body: ReopenRequest,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "POST /months/{month}/reopen", idempotency_key)
    return _write(request, commands.reopen_month(session, ctx, month, body, recalc))


@router.put(
    "/config/net-profit",
    response_model=SuccessEnvelope[NetProfitConfigResult, WriteMeta],
    responses=ERRORS,
    operation_id="updateSettlementProfitNetProfitConfig",
    summary="修改纯利设置（confirm_token = CONFIG YYYY-MM）",
)
def update_net_profit_config(
    request: Request,
    session: Db,
    access: Access,
    recalc: Recalc,
    body: NetProfitConfigUpdate,
    idempotency_key: IdempotencyKey,
):
    ctx = _ctx(request, access, "PUT /config/net-profit", idempotency_key)
    return _write(request, commands.update_config(session, ctx, body, recalc))
