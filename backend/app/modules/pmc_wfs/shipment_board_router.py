"""Read-only shipment board; Lingxing fulfillment arrives in a later slice."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_wfs.shipment_board_schemas import (
    ShipmentBoardDetail,
    ShipmentBoardFilter,
    ShipmentBoardList,
    ShipmentBoardOptions,
    ShipmentBoardQuery,
    ShipmentBoardSummary,
)
from app.modules.pmc_wfs.shipment_board_service import ShipmentBoardService

router = APIRouter(prefix="/api/pmc/wfs/shipment-board", tags=["PMC WFS Shipment Board"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 500, 503)}


def service(session: DB, accounts: Accounts, actor: Read):
    if "*" in actor.permissions:
        stores = None
    else:
        try:
            uid = int(actor.user_id)
        except ValueError:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
        values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
        stores = None if "*" in values else frozenset(values)
        if stores == frozenset():
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return ShipmentBoardService(session, accounts, stores)


Service = Annotated[ShipmentBoardService, Depends(service)]


def meta(extra: dict | None = None):
    base = {
        "source": "new_system_postgresql",
        "lingxing_sync_enabled": False,
        "source_tables": [
            "ops_wfs_creation_operations",
            "ops_wfs_creation_tickets",
            "ops_domestic_packing_orders",
            "dim_lingxing_stores",
        ],
    }
    if extra:
        base.update(extra)
    return base


@router.get("/shipments", response_model=SuccessEnvelope[ShipmentBoardList, dict], responses=ERRORS)
def shipments(request: Request, query: Annotated[ShipmentBoardQuery, Query()], svc: Service):
    data = svc.list(query)
    return success_response(request, data=data, meta=meta({"data_asof": data.data_asof.isoformat()}))


@router.get(
    "/shipments/{row_id:path}",
    response_model=SuccessEnvelope[ShipmentBoardDetail, dict],
    responses=ERRORS,
)
def shipment_detail(request: Request, row_id: str, svc: Service):
    return success_response(request, data=svc.detail(row_id), meta=meta())


@router.get("/summary", response_model=SuccessEnvelope[ShipmentBoardSummary, dict], responses=ERRORS)
def summary(request: Request, query: Annotated[ShipmentBoardFilter, Query()], svc: Service):
    return success_response(request, data=svc.summary(query), meta=meta())


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[ShipmentBoardOptions, dict],
    responses=ERRORS,
)
def filter_options(request: Request, svc: Service):
    return success_response(request, data=svc.options(), meta=meta())
