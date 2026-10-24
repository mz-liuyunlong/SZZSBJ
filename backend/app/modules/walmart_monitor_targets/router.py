from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import WALMART_MONITOR_TARGETS_READ_PERMISSION
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.walmart_monitor_targets.schemas import (
    MonitorTargetListData,
    MonitorTargetQuery,
    MonitorTargetReadMeta,
)
from app.modules.walmart_monitor_targets.service import WalmartMonitorTargetService

router = APIRouter(
    prefix="/api/integrations/walmart-monitor",
    tags=["Walmart Monitor Integration"],
)

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def get_walmart_monitor_target_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> WalmartMonitorTargetService:
    return WalmartMonitorTargetService(session)


@router.get(
    "/targets",
    response_model=SuccessEnvelope[MonitorTargetListData, MonitorTargetReadMeta],
    responses=ERRORS,
    dependencies=[Depends(require_permission(WALMART_MONITOR_TARGETS_READ_PERMISSION))],
    summary="List current Walmart monitoring targets",
    description=(
        "Returns a stable, read-only page of non-archived Listing monitoring targets. "
        "The request does not call external providers or trigger synchronization."
    ),
)
def list_monitor_targets(
    request: Request,
    query: Annotated[MonitorTargetQuery, Query()],
    service: Annotated[
        WalmartMonitorTargetService,
        Depends(get_walmart_monitor_target_service),
    ],
) -> SuccessEnvelope[MonitorTargetListData, MonitorTargetReadMeta]:
    data, meta = service.list_targets(query)
    return success_response(request, data=data, meta=meta)
