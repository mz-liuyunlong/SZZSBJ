from datetime import datetime
from typing import Annotated, Any

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
)
from app.modules.data_pages.service import DailySalesService
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(tags=["DATA-PAGES Daily Sales"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("sales:daily-sales:read"))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def _meta(
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


@router.get(
    "/api/sales/daily-sales",
    response_model=SuccessEnvelope[DailySalesListData, DailySalesReadMeta],
    responses=ERRORS,
)
def list_daily_sales(
    request: Request,
    query: Annotated[DailySalesQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[DailySalesListData, DailySalesReadMeta]:
    data, total, latest_calculated_at = DailySalesService(session).list_daily_sales(
        query,
        account_refs,
    )
    return success_response(
        request,
        data=data,
        meta=_meta(
            latest_calculated_at=latest_calculated_at,
            page=query.page,
            page_size=query.page_size,
            total=total,
            partial=any(item.cost_status != "complete" for item in data.items),
            input_missing=any(item.missing_cost_codes for item in data.items),
        ),
    )
