"""Protected Walmart SCF read endpoints with verified source-account scope."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.walmart_scf.store_scope import verify_http_store
from app.modules.walmart_scf.unified import approved_read, store_code_for

router = APIRouter(prefix="/api/integrations/walmart-scf", tags=["Walmart SCF Read"])


class ReadResponse(BaseModel):
    source_account_ref: str
    store_id: str
    operation: str
    http_status: int
    payload: Any


class ReadRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
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
    principal: Annotated[Principal, Depends(require_permission("integrations:execute"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[ReadResponse, None]:
    # POST is only a request envelope; the remote operation remains GET-only.
    verify_http_store(
        principal=principal,
        session=session,
        source_account_ref=payload.source_account_ref,
        store_id=payload.store_id,
        verified_source_account_scope=scope,
        store_code=store_code_for(payload.store_id),
    )
    result = approved_read(
        source_account_ref=payload.source_account_ref,
        store_id=payload.store_id,
        verified_store_scope=frozenset({payload.store_id}),
        verified_source_account_scope=scope,
        operation=payload.operation,
        params=payload.params,
    )
    return success_response(
        request,
        data=ReadResponse(
            source_account_ref=payload.source_account_ref,
            store_id=payload.store_id,
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
    store_id: Annotated[str, Query(min_length=1, max_length=128)],
    scope: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("integrations:execute"))],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 1,
) -> SuccessEnvelope[ReadResponse, None]:
    verify_http_store(
        principal=principal,
        session=session,
        source_account_ref=source_account_ref,
        store_id=store_id,
        verified_source_account_scope=scope,
        store_code=store_code_for(store_id),
    )
    result = approved_read(
        source_account_ref=source_account_ref,
        store_id=store_id,
        verified_store_scope=frozenset({store_id}),
        verified_source_account_scope=scope,
        operation="wfs_inventory",
        params={"limit": limit},
    )
    return success_response(
        request,
        data=ReadResponse(
            source_account_ref=source_account_ref,
            store_id=store_id,
            operation="wfs_inventory",
            http_status=result.status_code,
            payload=result.data,
        ),
        meta=None,
    )
