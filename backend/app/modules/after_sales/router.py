from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permission_policy_v2 import permission_for_request
from app.core.permissions import has_permission, require_permission
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
from app.modules.iam.organization_access import (
    ORG_OWNER_SCOPE_SESSION_KEY,
    resolve_business_owner_refs,
)
from app.modules.integration_sync.dependencies import require_source_account_scope

db_session = Annotated[Session, Depends(get_db_session)]
_ORG_SCOPED_REFUND_READS = frozenset(
    {
        "/api/after-sales/refunds/overview",
        "/api/after-sales/refunds/product-analysis",
        "/api/after-sales/refunds/items",
    }
)


def require_refund_org_scope(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    session: db_session,
) -> None:
    """A refund belongs to the reviewed product owner, not every store user."""
    session.info.pop(ORG_OWNER_SCOPE_SESSION_KEY, None)
    permission = permission_for_request(
        request.method, request.url.path, "aftersales:refund-management:read"
    )
    if not (
        has_permission(principal, permission)
        or has_permission(principal, "aftersales:refund-management:read")
    ):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    owners = resolve_business_owner_refs(session, principal)
    if owners is None:
        return
    if request.method != "GET" or request.url.path not in _ORG_SCOPED_REFUND_READS:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    session.info[ORG_OWNER_SCOPE_SESSION_KEY] = owners


router = APIRouter(
    tags=["AFTER-SALES-REFUNDS"],
    dependencies=[Depends(require_refund_org_scope)],
)
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
