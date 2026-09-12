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
from app.modules.products.dependencies import require_product_scope
from app.modules.sku_detail.schemas import (
    OperationLogQuery,
    SkuCostHistoryData,
    SkuDetailData,
    SkuLineageData,
    SkuListData,
    SkuListQuery,
    SkuOperationLogsData,
    SkuPageQuery,
    SkuPlatformListingsData,
    SkuReadMeta,
    SkuSyncHistoryData,
)
from app.modules.sku_detail.service import SkuDetailService

router = APIRouter(prefix="/api/products/skus", tags=["Lingxing SKU Detail"])

db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
products_principal = Annotated[Principal, Depends(require_permission("products:read"))]

audit_logger = logging.getLogger("app.audit.sku_detail")

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def _meta(
    *objects: str,
    freshness_at: datetime | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> SkuReadMeta:
    return SkuReadMeta(
        source_objects=list(objects),
        freshness_at=freshness_at,
        page=page,
        page_size=page_size,
        total=total,
    )


def _latest(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present, default=None)


@router.get(
    "",
    response_model=SuccessEnvelope[SkuListData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="listLingxingSkus",
)
def list_skus(
    request: Request,
    query: Annotated[SkuListQuery, Query()],
    session: db_session,
    _: products_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SkuListData, SkuReadMeta]:
    data, total = SkuDetailService(session).list_skus(query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dwd_lingxing_sku_identity_index",
            "dwd_lingxing_sku_product_info_current",
            "dws_sku_base_profile_current",
            freshness_at=_latest(
                *(
                    item.calculated_at or item.snapshot_at or item.last_seen_at
                    for item in data.items
                )
            ),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/{sku_id}/detail",
    response_model=SuccessEnvelope[SkuDetailData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="getLingxingSkuDetail",
)
def get_sku_detail(
    request: Request,
    sku_id: UUID,
    session: db_session,
    principal: products_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SkuDetailData, SkuReadMeta]:
    data = SkuDetailService(session).get_detail(
        sku_id,
        account_refs,
        include_costs="products:cost:read" in principal.permissions,
    )
    if "products:cost:read" in principal.permissions:
        audit_logger.info(
            "sku_cost_accessed actor_ref=%s request_id=%s sku_id=%s access_type=detail",
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
            "dwd_lingxing_sku_global_tags",
            "dws_sku_base_profile_current",
            freshness_at=_latest(
                data.profile.calculated_at if data.profile else None,
                data.detail.source_observed_at if data.detail else None,
                data.identity.last_seen_at,
            ),
        ),
    )


@router.get(
    "/{sku_id}/sync-history",
    response_model=SuccessEnvelope[SkuSyncHistoryData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="listLingxingSkuSyncHistory",
)
def get_sku_sync_history(
    request: Request,
    sku_id: UUID,
    query: Annotated[SkuPageQuery, Query()],
    session: db_session,
    _: Annotated[Principal, Depends(require_permission("products:sync_history:read"))],
    account_refs: source_scope,
) -> SuccessEnvelope[SkuSyncHistoryData, SkuReadMeta]:
    data, total = SkuDetailService(session).sync_history(sku_id, query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dwd_lingxing_sku_product_info_snapshots",
            "gov_integration_sync_runs",
            freshness_at=_latest(*(item.snapshot_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/{sku_id}/raw-lineage",
    response_model=SuccessEnvelope[SkuLineageData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="listLingxingSkuRawLineage",
)
def get_sku_raw_lineage(
    request: Request,
    sku_id: UUID,
    query: Annotated[SkuPageQuery, Query()],
    session: db_session,
    _: Annotated[Principal, Depends(require_permission("products:raw_lineage:read"))],
    account_refs: source_scope,
) -> SuccessEnvelope[SkuLineageData, SkuReadMeta]:
    data, total = SkuDetailService(session).raw_lineage(sku_id, query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_data_lineage",
            "ods_api_raw_blobs",
            freshness_at=_latest(*(item.received_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/{sku_id}/platform-listings",
    response_model=SuccessEnvelope[SkuPlatformListingsData, SkuReadMeta],
    responses=READ_ERRORS,
    dependencies=[Depends(require_product_scope)],
    operation_id="listLingxingSkuPlatformListings",
)
def get_sku_platform_listings(
    request: Request,
    sku_id: UUID,
    query: Annotated[SkuPageQuery, Query()],
    session: db_session,
    _: products_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[SkuPlatformListingsData, SkuReadMeta]:
    data, total = SkuDetailService(session).platform_listings(sku_id, query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "product_platform_listings",
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/{sku_id}/cost-history",
    response_model=SuccessEnvelope[SkuCostHistoryData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="listLingxingSkuCostHistory",
)
def get_sku_cost_history(
    request: Request,
    sku_id: UUID,
    query: Annotated[SkuPageQuery, Query()],
    session: db_session,
    principal: Annotated[Principal, Depends(require_permission("products:cost:read"))],
    account_refs: source_scope,
) -> SuccessEnvelope[SkuCostHistoryData, SkuReadMeta]:
    data, total = SkuDetailService(session).cost_history(sku_id, query, account_refs)
    audit_logger.info(
        "sku_cost_accessed actor_ref=%s request_id=%s sku_id=%s access_type=history",
        principal.user_id,
        get_request_id(request),
        sku_id,
    )
    return success_response(
        request,
        data=data,
        meta=_meta(
            "dwd_lingxing_sku_product_info_snapshots",
            freshness_at=_latest(*(item.source_observed_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/{sku_id}/operation-logs",
    response_model=SuccessEnvelope[SkuOperationLogsData, SkuReadMeta],
    responses=READ_ERRORS,
    operation_id="listLingxingSkuOperationLogs",
)
def get_sku_operation_logs(
    request: Request,
    sku_id: UUID,
    query: Annotated[OperationLogQuery, Query()],
    session: db_session,
    _: Annotated[Principal, Depends(require_permission("products:operation_logs:read"))],
    account_refs: source_scope,
) -> SuccessEnvelope[SkuOperationLogsData, SkuReadMeta]:
    data, total = SkuDetailService(session).operation_logs(sku_id, query, account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            "gov_integration_sync_run_events",
            freshness_at=_latest(*(item.occurred_at for item in data.items)),
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )
