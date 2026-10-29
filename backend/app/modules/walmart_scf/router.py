"""Protected Walmart SCF read endpoints with verified source-account scope."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.walmart_scf.unified import approved_read

router = APIRouter(prefix="/api/integrations/walmart-scf", tags=["Walmart SCF Read"])


class ReadResponse(BaseModel):
    source_account_ref: str
    operation: str
    http_status: int
    payload: Any


class ReadRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    operation: str = Field(min_length=2, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/read",
    response_model=SuccessEnvelope[ReadResponse, None],
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
    operation_id="readApprovedWalmartScfOperation",
)
def read_approved_operation(
    payload: ReadRequest,
    request: Request,
    scope: Annotated[frozenset[str], Depends(require_source_account_scope)],
    _: Annotated[Principal, Depends(require_permission("integrations:execute"))],
) -> SuccessEnvelope[ReadResponse, None]:
    # POST is merely a structured input envelope; the remote API remains GET-only.
    result = approved_read(
        source_account_ref=payload.source_account_ref,
        verified_source_account_scope=scope,
        operation=payload.operation,
        params=payload.params,
    )
    return success_response(
        request,
        data=ReadResponse(
            source_account_ref=payload.source_account_ref,
            operation=payload.operation,
            http_status=result.status_code,
            payload=result.data,
        ),
        meta=None,
    )


@router.get(
    "/wfs-inventory",
    response_model=SuccessEnvelope[ReadResponse, None],
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
    operation_id="readWalmartScfWfsInventory",
)
def get_wfs_inventory(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    scope: Annotated[frozenset[str], Depends(require_source_account_scope)],
    _: Annotated[Principal, Depends(require_permission("integrations:execute"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 1,
) -> SuccessEnvelope[ReadResponse, None]:
    result = approved_read(
        source_account_ref=source_account_ref,
        verified_source_account_scope=scope,
        operation="wfs_inventory",
        params={"limit": limit},
    )
    return success_response(
        request,
        data=ReadResponse(
            source_account_ref=source_account_ref,
            operation="wfs_inventory",
            http_status=result.status_code,
            payload=result.data,
        ),
        meta=None,
    )
