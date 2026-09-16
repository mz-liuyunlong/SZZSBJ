from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.data_pages.schemas import (
    DailySalesListData,
    DailySalesQuery,
    DailySalesReadMeta,
    OrderProfitListData,
    OrderProfitQuery,
    OrderProfitReadMeta,
)
from app.modules.data_pages.service import DailySalesService, OrderProfitService
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(tags=["DATA-PAGES Sales"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
daily_sales_principal = Annotated[
    Principal,
    Depends(require_permission("sales:daily-sales:read")),
]
order_profit_principal = Annotated[
    Principal,
    Depends(require_permission("sales:daily-sales:read")),
]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def _daily_sales_meta(
    *,
    latest_calculated_at: datetime | None,
    page: int,
    page_size: int,
    total: int,
    partial: bool,
    input_missing: bool,
) -> DailySalesReadMeta:
    return DailySalesReadMeta(
        source_objects=["mart_daily_sales_item_day"],
        latest_calculated_at=latest_calculated_at,
        page=page,
        page_size=page_size,
        total=total,
        partial=partial,
        input_missing=input_missing,
    )


def _order_profit_meta(
    *,
    latest_calculated_at: datetime | None,
    page: int,
    page_size: int,
    total: int,
    partial: bool,
    input_missing: bool,
) -> OrderProfitReadMeta:
    return OrderProfitReadMeta(
        source_objects=["mart_order_profit_sku_day"],
        latest_calculated_at=latest_calculated_at,
        page=page,
        page_size=page_size,
        total=total,
        partial=partial,
        input_missing=input_missing,
    )


def _has_missing_costs(items: Any) -> bool:
    return any(item.missing_cost_codes for item in items)


def _is_partial(items: Any) -> bool:
    return any(item.cost_status != "complete" for item in items)


@router.get(
    "/api/sales/daily-sales",
    response_model=SuccessEnvelope[DailySalesListData, DailySalesReadMeta],
    responses=ERRORS,
)
def list_daily_sales(
    request: Request,
    query: Annotated[DailySalesQuery, Query()],
    session: db_session,
    _: daily_sales_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[DailySalesListData, DailySalesReadMeta]:
    data, total, latest_calculated_at = DailySalesService(session).list_daily_sales(
        query,
        account_refs,
    )
    return success_response(
        request,
        data=data,
        meta=_daily_sales_meta(
            latest_calculated_at=latest_calculated_at,
            page=query.page,
            page_size=query.page_size,
            total=total,
            partial=_is_partial(data.items),
            input_missing=_has_missing_costs(data.items),
        ),
    )


@router.get(
    "/api/sales/order-profit",
    response_model=SuccessEnvelope[OrderProfitListData, OrderProfitReadMeta],
    responses=ERRORS,
)
def list_order_profit(
    request: Request,
    query: Annotated[OrderProfitQuery, Query()],
    session: db_session,
    _: order_profit_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[OrderProfitListData, OrderProfitReadMeta]:
    data, total, latest_calculated_at = OrderProfitService(session).list_order_profit(
        query,
        account_refs,
    )
    return success_response(
        request,
        data=data,
        meta=_order_profit_meta(
            latest_calculated_at=latest_calculated_at,
            page=query.page,
            page_size=query.page_size,
            total=total,
            partial=_is_partial(data.items),
            input_missing=_has_missing_costs(data.items),
        ),
    )
