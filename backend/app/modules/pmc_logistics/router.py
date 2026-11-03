"""物流看板 API (read-only): 8088 ``pmc-logistics`` over stored Lingxing / 众壹 / Walmart
records. No provider calls, no writes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_logistics.schemas import LogisticsBoard, LogisticsDetail
from app.modules.pmc_logistics.service import LogisticsService

router = APIRouter(prefix="/api/pmc/logistics", tags=["PMC Logistics"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
# Same page permission as the WFS board until a logistics key is approved (PRP #298).
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 500, 503)}


def service(session: DB, accounts: Accounts, actor: Read) -> LogisticsService:
    if "*" in actor.permissions:
        stores = None
    else:
        try:
            uid = int(actor.user_id)
        except ValueError:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
        values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
        stores = None if "*" in values else set(values)
        if stores == set():
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return LogisticsService(session, sorted(accounts), stores)


Service = Annotated[LogisticsService, Depends(service)]


def meta(svc: LogisticsService) -> dict:
    snap = svc.snapshot()
    return {
        "source": "new_system_postgresql",
        "rule_date": snap.today.isoformat(),
        "provider_calls": False,
        "source_tables": [
            "gov_wfs_board_publications",
            "ods_lingxing_wfs_shipping_lists",
            "ods_lingxing_wfs_cargos",
            "ods_lingxing_logistics_channels",
            "ods_carrier_zhongyi_orders",
            "ods_carrier_zhongyi_tracks",
            "ods_walmart_wfs_inbound_shipments",
            "ods_walmart_wfs_receipts",
        ],
    }


@router.get("/board", response_model=SuccessEnvelope[LogisticsBoard, dict], responses=ERRORS)
def board(request: Request, svc: Service):
    return success_response(request, data=svc.board(), meta=meta(svc))


@router.get(
    "/shipping-lists/{code}",
    response_model=SuccessEnvelope[LogisticsDetail, dict],
    responses=ERRORS,
)
def shipping_list(
    request: Request, svc: Service, code: Annotated[str, Path(min_length=1, max_length=64)]
):
    data = svc.detail(code)
    if data is None:
        raise ApiError(
            code=ErrorCode.NOT_FOUND, status_code=404, message="发货单不存在或不在数据范围内"
        )
    return success_response(request, data=data, meta=meta(svc))
