from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import has_permission
from app.db.session import get_db_session
from app.modules.walmart_monitor.schemas import (
    WalmartMonitorRawEventAccepted,
    WalmartMonitorRawEventRequest,
)
from app.modules.walmart_monitor.service import WalmartMonitorIngestionService

MONITOR_WRITE_PERMISSION = "integrations:walmart-monitor:write"

router = APIRouter(
    prefix="/api/integrations/walmart-monitor",
    tags=["Walmart Monitor Integration"],
)

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


def require_monitor_writer(
    principal: Annotated[Principal, Depends(require_principal)],
) -> Principal:
    if has_permission(principal, MONITOR_WRITE_PERMISSION):
        return principal
    raise ApiError(code="FORBIDDEN", status_code=403)


@router.post(
    "/raw-events",
    response_model=SuccessEnvelope[WalmartMonitorRawEventAccepted, None],
    responses=ERRORS,
    status_code=status.HTTP_201_CREATED,
    operation_id="ingestWalmartMonitorRawEvent",
)
def ingest_walmart_monitor_raw_event(
    payload: WalmartMonitorRawEventRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[Principal, Depends(require_monitor_writer)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
) -> SuccessEnvelope[WalmartMonitorRawEventAccepted, None]:
    result = WalmartMonitorIngestionService(session).ingest(
        payload,
        idempotency_key=idempotency_key,
    )
    return success_response(
        request,
        data=WalmartMonitorRawEventAccepted(
            id=result.id,
            event_id=result.event_id,
            duplicate=result.duplicate,
            received_at=result.received_at,
        ),
        meta=None,
    )
