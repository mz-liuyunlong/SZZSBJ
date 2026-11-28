"""WooCommerce product management: authenticated catalog access."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.modules.woocommerce_config.service import WooCommerceConfigError

from .service import (
    ListingLookup,
    RuleWrite,
    read_catalog,
    read_listing_links,
    read_rules,
    read_sync_stores,
    save_rules,
)

router = APIRouter(prefix="/api/woocommerce/products", tags=["WooCommerce products"])
User = Annotated[Principal, Depends(require_principal)]


@router.get(
    "", response_model=SuccessEnvelope[dict[str, object], None], operation_id="listWooCatalog"
)
def list_products(
    request: Request,
    _: User,
    page: int = Query(1, ge=1, le=1000000),
    page_size: int = Query(50, ge=1, le=1000),
    keyword: str = Query("", max_length=255),
    search_type: Literal["all", "name", "sku", "id"] = "all",
    store: Annotated[list[UUID] | None, Query()] = None,
    brand: Annotated[list[str] | None, Query()] = None,
    stock: Annotated[list[str] | None, Query()] = None,
    description: Annotated[list[Literal["complete", "unconfirmed"]] | None, Query()] = None,
    status: Literal["all", "publish", "draft", "pending", "private", "other"] = "all",
    sort_key: str = Query("listedAt", max_length=32),
    sort_order: Literal["ascend", "descend"] = "descend",
):
    store = store or []
    brand = brand or []
    stock = stock or []
    description = description or []
    if any(len(v) > 200 for v in (store, brand, stock, description)):
        raise ApiError(code="WOO_FILTER_LIMIT", status_code=422)
    try:
        return success_response(
            request,
            data=read_catalog(
                page=page,
                page_size=page_size,
                keyword=keyword,
                search_type=search_type,
                stores_filter=store,
                brands_filter=brand,
                stock_filter=stock,
                description_filter=description,
                status=status,
                sort_key=sort_key,
                sort_order=sort_order,
            ),
            meta=None,
        )
    except WooCommerceConfigError as exc:
        raise ApiError(code=exc.code, status_code=exc.status) from None


@router.get(
    "/rules",
    response_model=SuccessEnvelope[dict[str, object], None],
    operation_id="getWooProductRules",
)
def get_rules(request: Request, _: User):
    try:
        return success_response(request, data=read_rules(), meta=None)
    except WooCommerceConfigError as exc:
        raise ApiError(code=exc.code, status_code=exc.status) from None


@router.put(
    "/rules",
    response_model=SuccessEnvelope[dict[str, object], None],
    operation_id="saveWooProductRules",
)
def put_rules(request: Request, payload: RuleWrite, principal: User):
    try:
        return success_response(
            request, data=save_rules(payload, actor=principal.user_id), meta=None
        )
    except WooCommerceConfigError as exc:
        raise ApiError(code=exc.code, status_code=exc.status) from None


@router.post(
    "/listing-links",
    response_model=SuccessEnvelope[list[dict[str, object]], None],
    operation_id="lookupWooListingLinks",
)
def listing_links(request: Request, payload: ListingLookup, _: User):
    return success_response(request, data=read_listing_links(payload), meta=None)


@router.get(
    "/sync-stores",
    response_model=SuccessEnvelope[list[dict[str, str]], None],
    operation_id="listWooSyncStoreLabels",
)
def sync_store_labels(request: Request, _: User):
    return success_response(request, data=read_sync_stores(), meta=None)
