from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_super_admin

from .schemas import (
    WooCommerceStoreCreate,
    WooCommerceStoreRead,
    WooCommerceStoreUpdate,
    WooCommerceTestResult,
)
from .service import (
    WooCommerceConfigError,
    create_store,
    list_stores,
    test_store,
    update_store,
)

router = APIRouter(
    prefix="/api/system-config/woocommerce/stores",
    tags=["System Config - WooCommerce"],
)
read_principal = Annotated[Principal, Depends(require_super_admin)]
admin_principal = Annotated[Principal, Depends(require_super_admin)]


def _api_error(exc: WooCommerceConfigError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status)


@router.get(
    "",
    response_model=SuccessEnvelope[list[WooCommerceStoreRead], None],
    operation_id="listWooCommerceStores",
)
def get_stores(
    request: Request,
    _: read_principal,
) -> SuccessEnvelope[list[WooCommerceStoreRead], None]:
    try:
        return success_response(request, data=list_stores(), meta=None)
    except WooCommerceConfigError as exc:
        raise _api_error(exc) from None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[WooCommerceStoreRead, None],
    operation_id="createWooCommerceStore",
)
def post_store(
    request: Request,
    payload: WooCommerceStoreCreate,
    principal: admin_principal,
) -> SuccessEnvelope[WooCommerceStoreRead, None]:
    try:
        value = create_store(payload, actor=principal.user_id)
        return success_response(request, data=value, meta=None)
    except WooCommerceConfigError as exc:
        raise _api_error(exc) from None


@router.put(
    "/{store_id}",
    response_model=SuccessEnvelope[WooCommerceStoreRead, None],
    operation_id="updateWooCommerceStore",
)
def put_store(
    request: Request,
    store_id: UUID,
    payload: WooCommerceStoreUpdate,
    principal: admin_principal,
) -> SuccessEnvelope[WooCommerceStoreRead, None]:
    try:
        value = update_store(store_id, payload, actor=principal.user_id)
        return success_response(request, data=value, meta=None)
    except WooCommerceConfigError as exc:
        raise _api_error(exc) from None


@router.post(
    "/{store_id}/test",
    response_model=SuccessEnvelope[WooCommerceTestResult, None],
    operation_id="testWooCommerceStoreConnection",
)
def post_test(
    request: Request,
    store_id: UUID,
    principal: admin_principal,
) -> SuccessEnvelope[WooCommerceTestResult, None]:
    try:
        value = test_store(store_id, actor=principal.user_id)
        return success_response(request, data=value, meta=None)
    except WooCommerceConfigError as exc:
        raise _api_error(exc) from None
