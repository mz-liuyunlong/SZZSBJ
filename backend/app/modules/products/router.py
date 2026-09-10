from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.products.dependencies import require_product_scope
from app.modules.products.schemas import (
    ProductCreate,
    ProductListData,
    ProductListingCreate,
    ProductListingListData,
    ProductListingListQuery,
    ProductListingRead,
    ProductListingUpdate,
    ProductListQuery,
    ProductOptionsData,
    ProductRead,
    ProductUpdate,
)
from app.modules.products.service import ProductService

router = APIRouter(prefix="/api/v1/products", tags=["Product Management"])

products_read = require_permission("products:read")
products_create = require_permission("products:create")
products_update = require_permission("products:update")
listings_read = require_permission("product_listings:read")
listings_create = require_permission("product_listings:create")
listings_update = require_permission("product_listings:update")

scope_dependency = Depends(require_product_scope)
db_session = Annotated[Session, Depends(get_db_session)]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **READ_ERRORS,
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


@router.get(
    "",
    response_model=SuccessEnvelope[ProductListData, None],
    responses=READ_ERRORS,
    dependencies=[Depends(products_read), scope_dependency],
)
def list_products(
    request: Request,
    query: Annotated[ProductListQuery, Query()],
    session: db_session,
) -> SuccessEnvelope[ProductListData, None]:
    return success_response(request, data=ProductService(session).list_products(query), meta=None)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[ProductRead, None],
    responses=WRITE_ERRORS,
    dependencies=[Depends(products_create), scope_dependency],
)
def create_product(
    request: Request,
    payload: ProductCreate,
    session: db_session,
) -> SuccessEnvelope[ProductRead, None]:
    return success_response(
        request, data=ProductService(session).create_product(payload), meta=None
    )


@router.get(
    "/options",
    response_model=SuccessEnvelope[ProductOptionsData, None],
    responses=READ_ERRORS,
    dependencies=[Depends(products_read), scope_dependency],
)
def product_options(request: Request) -> SuccessEnvelope[ProductOptionsData, None]:
    return success_response(request, data=ProductService.options(), meta=None)


@router.get(
    "/{product_id}",
    response_model=SuccessEnvelope[ProductRead, None],
    responses=READ_ERRORS,
    dependencies=[Depends(products_read), scope_dependency],
)
def get_product(
    request: Request,
    product_id: UUID,
    session: db_session,
) -> SuccessEnvelope[ProductRead, None]:
    return success_response(
        request, data=ProductService(session).get_product(product_id), meta=None
    )


@router.patch(
    "/{product_id}",
    response_model=SuccessEnvelope[ProductRead, None],
    responses=WRITE_ERRORS,
    dependencies=[Depends(products_update), scope_dependency],
)
def update_product(
    request: Request,
    product_id: UUID,
    payload: ProductUpdate,
    session: db_session,
) -> SuccessEnvelope[ProductRead, None]:
    return success_response(
        request,
        data=ProductService(session).update_product(product_id, payload),
        meta=None,
    )


@router.get(
    "/{product_id}/listings",
    response_model=SuccessEnvelope[ProductListingListData, None],
    responses=READ_ERRORS,
    dependencies=[Depends(listings_read), scope_dependency],
)
def list_product_listings(
    request: Request,
    product_id: UUID,
    query: Annotated[ProductListingListQuery, Query()],
    session: db_session,
) -> SuccessEnvelope[ProductListingListData, None]:
    return success_response(
        request,
        data=ProductService(session).list_listings(product_id, query),
        meta=None,
    )


@router.post(
    "/{product_id}/listings",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[ProductListingRead, None],
    responses=WRITE_ERRORS,
    dependencies=[Depends(listings_create), scope_dependency],
)
def create_product_listing(
    request: Request,
    product_id: UUID,
    payload: ProductListingCreate,
    session: db_session,
) -> SuccessEnvelope[ProductListingRead, None]:
    return success_response(
        request,
        data=ProductService(session).create_listing(product_id, payload),
        meta=None,
    )


@router.patch(
    "/{product_id}/listings/{listing_id}",
    response_model=SuccessEnvelope[ProductListingRead, None],
    responses=WRITE_ERRORS,
    dependencies=[Depends(listings_update), scope_dependency],
)
def update_product_listing(
    request: Request,
    product_id: UUID,
    listing_id: UUID,
    payload: ProductListingUpdate,
    session: db_session,
) -> SuccessEnvelope[ProductListingRead, None]:
    return success_response(
        request,
        data=ProductService(session).update_listing(product_id, listing_id, payload),
        meta=None,
    )
