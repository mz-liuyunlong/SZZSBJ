import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.product_management.schemas import (
    ExportRequest,
    ExportResult,
    PricingBreakdownRead,
    PricingRuleRead,
    PricingRulesData,
    PricingRuleWrite,
    ProductManagementDetailData,
    ProductManagementListData,
    ProductManagementListQuery,
    ProductManagementOptionsData,
    ProductManagementReadMeta,
    ProductManagementSummaryData,
    ProductManagementSummaryQuery,
    RecalculatePricingRequest,
    RecalculatePricingResult,
    UserTableViewRead,
    UserTableViewWrite,
)
from app.modules.product_management.service import ProductManagementService
from app.modules.products.dependencies import require_product_scope

router = APIRouter(tags=["Product Management BFF"])
db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("products:read"))]
audit_logger = logging.getLogger("app.audit.product_management")

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    424: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}
product_scope_dependency = Depends(require_product_scope)


def _meta(
    *objects: str,
    list_freshness_at: datetime | None = None,
    latest_observed_at: datetime | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
    stale: bool | None = None,
    partial: bool = False,
    input_missing: bool = False,
) -> ProductManagementReadMeta:
    return ProductManagementReadMeta(
        source_objects=list(objects),
        list_freshness_at=list_freshness_at,
        latest_observed_at=latest_observed_at,
        page=page,
        page_size=page_size,
        total=total,
        stale=stale,
        partial=partial,
        input_missing=input_missing,
    )


@router.get(
    "/api/product-management/skus",
    response_model=SuccessEnvelope[ProductManagementListData, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def list_product_management_skus(
    request: Request,
    query: Annotated[ProductManagementListQuery, Query()],
    session: db_session,
    principal: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[ProductManagementListData, ProductManagementReadMeta]:
    data, total, list_freshness, latest_observed = ProductManagementService(session).list_skus(
        query,
        account_refs,
        include_costs="products:cost:read" in principal.permissions,
    )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "products",
            "dwd_lingxing_sku_identity_index",
            "dwd_lingxing_sku_product_info_current",
            "dwd_lingxing_sku_product_images",
            "dws_sku_base_profile_current",
            "dws_product_management_pricing_current",
            list_freshness_at=list_freshness,
            latest_observed_at=latest_observed,
            page=query.page,
            page_size=query.page_size,
            total=total,
            partial=any(not item.pricing_available for item in data.items),
            input_missing=any(item.root_missing_codes for item in data.items),
        ),
    )


@router.get(
    "/api/product-management/skus/summary",
    response_model=SuccessEnvelope[ProductManagementSummaryData, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def summarize_product_management_skus(
    request: Request,
    query: Annotated[ProductManagementSummaryQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[ProductManagementSummaryData, ProductManagementReadMeta]:
    data = ProductManagementService(session).summary(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dwd_lingxing_sku_identity_index",
            "dwd_lingxing_sku_product_info_current",
            "dwd_lingxing_sku_product_images",
            "dwd_lingxing_sku_global_tags",
            "dws_sku_base_profile_current",
            total=data.total,
        ),
    )


@router.get(
    "/api/product-management/options",
    response_model=SuccessEnvelope[ProductManagementOptionsData, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def get_product_management_options(
    request: Request,
    query: Annotated[ProductManagementSummaryQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[ProductManagementOptionsData, ProductManagementReadMeta]:
    return success_response(
        request,
        data=ProductManagementService(session).options(account_refs, query),
        meta=_meta(
            "manual_product_tags",
            "dwd_lingxing_sku_identity_index",
            "dwd_lingxing_sku_product_info_current",
            "dwd_lingxing_sku_global_tags",
            "dws_product_management_pricing_current",
        ),
    )


@router.post(
    "/api/product-management/skus/export",
    response_model=SuccessEnvelope[ExportResult, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[
        Depends(require_permission("products:export")),
        product_scope_dependency,
    ],
)
def export_product_management_skus(
    request: Request,
    payload: ExportRequest,
    principal: read_principal,
    _: source_scope,
) -> SuccessEnvelope[ExportResult, ProductManagementReadMeta]:
    audit_logger.info(
        "product_export_requested actor_ref=%s request_id=%s "
        "row_limit=%s status=not_implemented_safe",
        principal.user_id,
        get_request_id(request),
        payload.max_rows,
    )
    return success_response(
        request,
        data=ProductManagementService.export(payload),
        meta=_meta("products", "dws_product_management_pricing_current"),
    )


@router.post(
    "/api/product-management/skus/recalculate-pricing",
    response_model=SuccessEnvelope[RecalculatePricingResult, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[
        Depends(require_permission("products:pricing:recalculate")),
        product_scope_dependency,
    ],
)
def recalculate_product_management_pricing(
    request: Request,
    payload: RecalculatePricingRequest,
    session: db_session,
    principal: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[RecalculatePricingResult, ProductManagementReadMeta]:
    data = ProductManagementService(session).recalculate(
        payload,
        account_refs,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
    )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dws_product_management_pricing_current",
            "product_pricing_recalculation_runs",
            "ref_product_pricing_rule_versions",
        ),
    )


@router.get(
    "/api/product-management/skus/{sku_id}",
    response_model=SuccessEnvelope[ProductManagementDetailData, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def get_product_management_sku(
    request: Request,
    sku_id: UUID,
    session: db_session,
    principal: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[ProductManagementDetailData, ProductManagementReadMeta]:
    include_costs = "products:cost:read" in principal.permissions
    data = ProductManagementService(session).get_sku(
        sku_id, account_refs, include_costs=include_costs
    )
    if include_costs:
        audit_logger.info(
            "product_management_cost_accessed actor_ref=%s request_id=%s sku_id=%s",
            principal.user_id,
            get_request_id(request),
            sku_id,
        )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "products",
            "dwd_lingxing_sku_product_info_current",
            "dwd_lingxing_sku_product_images",
            "dwd_lingxing_sku_global_tags",
            "dws_sku_base_profile_current",
            "dws_product_management_pricing_current",
        ),
    )


@router.get(
    "/api/product-management/skus/{sku_id}/pricing-breakdown",
    response_model=SuccessEnvelope[PricingBreakdownRead, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def get_product_management_pricing_breakdown(
    request: Request,
    sku_id: UUID,
    session: db_session,
    principal: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[PricingBreakdownRead, ProductManagementReadMeta]:
    include_costs = "products:cost:read" in principal.permissions
    data = ProductManagementService(session).pricing_breakdown(
        sku_id, account_refs, include_costs=include_costs
    )
    if include_costs:
        audit_logger.info(
            "product_management_pricing_breakdown_accessed actor_ref=%s request_id=%s sku_id=%s",
            principal.user_id,
            get_request_id(request),
            sku_id,
        )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dwd_lingxing_sku_product_info_current",
            "dwd_lingxing_sku_product_images",
            "dws_sku_base_profile_current",
            "ref_product_pricing_rule_versions",
        ),
    )


@router.get(
    "/api/product-management/pricing-rules",
    response_model=SuccessEnvelope[PricingRulesData, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[
        Depends(require_permission("products:pricing_rules:read")),
        product_scope_dependency,
    ],
)
def get_product_management_pricing_rules(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: db_session,
    account_refs: source_scope,
) -> SuccessEnvelope[PricingRulesData, ProductManagementReadMeta]:
    return success_response(
        request,
        data=ProductManagementService(session).list_rules(source_account_ref, account_refs),
        meta=_meta("ref_product_pricing_rule_versions"),
    )


@router.put(
    "/api/product-management/pricing-rules",
    response_model=SuccessEnvelope[PricingRuleRead, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def put_product_management_pricing_rule(
    request: Request,
    payload: PricingRuleWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission("products:pricing_rules:update"))],
    account_refs: source_scope,
) -> SuccessEnvelope[PricingRuleRead, ProductManagementReadMeta]:
    data = ProductManagementService(session).publish_rule(
        payload,
        account_refs,
        actor_ref=principal.user_id,
        request_id=get_request_id(request),
    )
    return success_response(request, data=data, meta=_meta("ref_product_pricing_rule_versions"))


@router.get(
    "/api/user-table-views/product-management",
    response_model=SuccessEnvelope[UserTableViewRead, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def get_product_management_table_view(
    request: Request,
    session: db_session,
    principal: read_principal,
) -> SuccessEnvelope[UserTableViewRead, ProductManagementReadMeta]:
    return success_response(
        request,
        data=ProductManagementService(session).get_table_view(principal.user_id),
        meta=_meta("user_table_views"),
    )


@router.put(
    "/api/user-table-views/product-management",
    response_model=SuccessEnvelope[UserTableViewRead, ProductManagementReadMeta],
    responses=ERRORS,
    dependencies=[product_scope_dependency],
)
def put_product_management_table_view(
    request: Request,
    payload: UserTableViewWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission("products:table_views:update"))],
) -> SuccessEnvelope[UserTableViewRead, ProductManagementReadMeta]:
    data = ProductManagementService(session).save_table_view(
        payload, principal_ref=principal.user_id
    )
    return success_response(request, data=data, meta=_meta("user_table_views"))
