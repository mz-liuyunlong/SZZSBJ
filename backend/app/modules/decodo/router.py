"""Authenticated backend-only Decodo configuration and product research routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import has_permission, require_permission, require_super_admin
from app.modules.decodo import local_test
from app.modules.decodo.parse import amazon_document, walmart_document
from app.modules.decodo.schemas import (
    AmazonResearchRequest,
    AmazonResearchResult,
    DecodoConfigRead,
    DecodoConfigWrite,
    DecodoUsageRead,
    WalmartConfirmRequest,
    WalmartFactRead,
)
from app.modules.decodo.service import (
    DecodoError,
    config_read,
    config_write,
    save_snapshot,
    scrape,
    usage_read,
)

settings_router = APIRouter(prefix="/api/business-rules/decodo", tags=["Decodo Configuration"])
research_router = APIRouter(prefix="/api/keyword-planning", tags=["Keyword Research"])
read_perm = Annotated[Principal, Depends(require_permission("business-rules:read"))]
write_perm = Annotated[Principal, Depends(require_super_admin)]
def require_decodo_research_access(
    principal: Annotated[Principal, Depends(require_principal)],
) -> Principal:
    # Existing products:read permission remains valid in all environments.
    if has_permission(principal, "products:read"):
        return principal
    # The standard RBAC product-page view permission grants research execution
    # ONLY in explicitly opted-in local SQLite mode, not production.
    if local_test.is_enabled() and has_permission(
        principal, "page:products:product-management:view"
    ):
        return principal
    raise ApiError(code="FORBIDDEN", status_code=403)


product_perm = Annotated[Principal, Depends(require_decodo_research_access)]


def _safe_error(exc: DecodoError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status)


@settings_router.get("", response_model=SuccessEnvelope[DecodoConfigRead, Any])
def get_config(request: Request, _: read_perm) -> SuccessEnvelope[DecodoConfigRead, Any]:
    return success_response(request, data=config_read(), meta=None)


@settings_router.put("", response_model=SuccessEnvelope[DecodoConfigRead, Any])
def put_config(
    request: Request, payload: DecodoConfigWrite, principal: write_perm
) -> SuccessEnvelope[DecodoConfigRead, Any]:
    try:
        value = config_write(
            authorization=payload.authorization,
            zip_code=payload.us_zip,
            enabled=payload.enabled,
            actor=principal.user_id,
        )
    except DecodoError as exc:
        raise _safe_error(exc) from None
    return success_response(request, data=value, meta=None)


@settings_router.get("/usage", response_model=SuccessEnvelope[DecodoUsageRead, Any])
def get_usage(
    request: Request, _: read_perm, days: Annotated[int, Query(ge=1, le=31)] = 7
) -> SuccessEnvelope[DecodoUsageRead, Any]:
    return success_response(request, data=usage_read(days), meta=None)


@research_router.post("/products/confirm", response_model=SuccessEnvelope[WalmartFactRead, Any])
async def confirm_product(
    request: Request, payload: WalmartConfirmRequest, principal: product_perm
) -> SuccessEnvelope[WalmartFactRead, Any]:
    try:
        raw = await scrape(
            target="walmart_product", identifier=payload.item_id, actor=principal.user_id
        )
        result = walmart_document(raw, payload.item_id, payload.sku_id)
        result.snapshot_id = save_snapshot(
            target="walmart_product",
            sku_id=payload.sku_id,
            identifier=payload.item_id,
            data=result.model_dump(mode="json"),
            actor=principal.user_id,
        )
    except DecodoError as exc:
        raise _safe_error(exc) from None
    except ValueError as exc:
        raise ApiError(code=str(exc), status_code=422) from None
    return success_response(request, data=result, meta=None)


@research_router.post("/amazon/research", response_model=SuccessEnvelope[AmazonResearchResult, Any])
async def research_amazon(
    request: Request, payload: AmazonResearchRequest, principal: product_perm
) -> SuccessEnvelope[AmazonResearchResult, Any]:
    # Limit concurrency and wait for each requested ASIN; a failed item does not erase successes.
    semaphore = asyncio.Semaphore(3)

    async def one(asin: str):
        async with semaphore:
            try:
                raw = await scrape(
                    target="amazon_product", identifier=asin, actor=principal.user_id
                )
                doc = amazon_document(raw, asin)
                doc.snapshot_id = save_snapshot(
                    target="amazon_product",
                    sku_id=payload.sku_id,
                    identifier=asin,
                    data=doc.model_dump(mode="json"),
                    actor=principal.user_id,
                )
                return doc
            except (DecodoError, ValueError):
                return None

    documents = await asyncio.gather(*(one(asin) for asin in payload.asins))
    successes = [doc for doc in documents if doc is not None]
    failures = [asin for asin, doc in zip(payload.asins, documents, strict=True) if doc is None]
    result = AmazonResearchResult(
        items=successes,
        failures=failures,
        requested=len(payload.asins),
        completed=len(successes),
    )
    return success_response(request, data=result, meta=None)
