from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.after_sales.schemas import (
    RefundBaseQuery,
    RefundItemListData,
    RefundItemListMeta,
    RefundItemQuery,
    RefundOverviewData,
    RefundProductAnalysisData,
    RefundProductAnalysisQuery,
    RefundReadMeta,
)
from app.modules.after_sales.service import AfterSalesRefundService
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(tags=["AFTER-SALES-REFUNDS"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[
    Principal,
    Depends(require_permission("aftersales:refund-management:read")),
]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


@router.get(
    "/api/after-sales/refunds/overview",
    response_model=SuccessEnvelope[RefundOverviewData, RefundReadMeta],
    responses=ERRORS,
)
def refund_overview(
    request: Request,
    query: Annotated[RefundBaseQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[RefundOverviewData, RefundReadMeta]:
    service = AfterSalesRefundService(session)
    data = service.overview(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=RefundReadMeta(
            source_objects=service.source_objects,
            start_date=query.start_date,
            end_date=query.end_date,
            latest_updated_at=service.latest_updated_at(query, account_refs),
        ),
    )


@router.get(
    "/api/after-sales/refunds/product-analysis",
    response_model=SuccessEnvelope[RefundProductAnalysisData, RefundReadMeta],
    responses=ERRORS,
)
def refund_product_analysis(
    request: Request,
    query: Annotated[RefundProductAnalysisQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[RefundProductAnalysisData, RefundReadMeta]:
    service = AfterSalesRefundService(session)
    data = service.product_analysis(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=RefundReadMeta(
            source_objects=service.source_objects,
            start_date=query.start_date,
            end_date=query.end_date,
            latest_updated_at=service.latest_updated_at(query, account_refs),
        ),
    )


@router.get(
    "/api/after-sales/refunds/items",
    response_model=SuccessEnvelope[RefundItemListData, RefundItemListMeta],
    responses=ERRORS,
)
def refund_items(
    request: Request,
    query: Annotated[RefundItemQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[RefundItemListData, RefundItemListMeta]:
    service = AfterSalesRefundService(session)
    data, total, latest = service.list_items(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=RefundItemListMeta(
            source_objects=service.source_objects,
            start_date=query.start_date,
            end_date=query.end_date,
            latest_updated_at=latest,
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )
