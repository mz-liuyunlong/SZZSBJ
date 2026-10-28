"""Opt-in store-scoped Walmart read endpoint; no persistence or Celery dispatch."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.walmart_scf.service import read_wfs_inventory

router = APIRouter(prefix="/api/integrations/walmart-scf", tags=["Walmart SCF Read"])


class WfsInventoryRead(BaseModel):
    store_code: str
    http_status: int
    payload: Any


@router.get(
    "/wfs-inventory",
    response_model=SuccessEnvelope[WfsInventoryRead, None],
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
    store_code: Annotated[str, Query(min_length=6, max_length=6)],
    verified_scope: Annotated[frozenset[str], Depends(require_source_account_scope)],
    _: Annotated[Principal, Depends(require_permission("integrations:execute"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 1,
) -> SuccessEnvelope[WfsInventoryRead, None]:
    result = read_wfs_inventory(
        store_code=store_code,
        verified_source_account_scope=verified_scope,
        limit=limit,
    )
    return success_response(
        request,
        data=WfsInventoryRead(
            store_code=store_code, http_status=result.status_code, payload=result.data
        ),
        meta=None,
    )
