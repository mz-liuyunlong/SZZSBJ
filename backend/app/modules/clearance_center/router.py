"""Real WFS clearance API: scoped reads, governed requests and manual progress."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.clearance_center.schemas import (
    ApplicationWrite,
    ListingQuery,
    ProgressWrite,
    RuleWrite,
)
from app.modules.clearance_center.service import ClearanceService
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(prefix="/api/products/clearance-center", tags=["WFS Clearance"])
db_session = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
reader = Annotated[Principal, Depends(require_permission("products:read"))]
applicant = Annotated[Principal, Depends(require_permission("action:products:clearance:apply"))]
operator = Annotated[Principal, Depends(require_permission("action:products:clearance:progress"))]
configurer = Annotated[
    Principal, Depends(require_permission("action:products:clearance:configure"))
]


@router.get("/listings", response_model=SuccessEnvelope[dict[str, Any], None])
def listings(
    request: Request,
    query: Annotated[ListingQuery, Query()],
    session: db_session,
    _: reader,
    accounts: scope,
):
    data = ClearanceService(session).list_listings(
        accounts,
        store_id=query.store_id,
        keyword=query.keyword,
        risk_level=query.risk_level,
        candidate_status=query.candidate_status,
        page=query.page,
        page_size=query.page_size,
    )
    return success_response(request, data=data, meta=None)


@router.get("/eligible-listings", response_model=SuccessEnvelope[dict[str, Any], None])
def eligible_listings(
    request: Request,
    query: Annotated[ListingQuery, Query()],
    session: db_session,
    _: applicant,
    accounts: scope,
):
    data = ClearanceService(session).list_listings(
        accounts,
        store_id=query.store_id,
        keyword=query.keyword,
        eligible_only=True,
        page=query.page,
        page_size=query.page_size,
    )
    return success_response(request, data=data, meta=None)


@router.get("/summary", response_model=SuccessEnvelope[dict[str, Any], None])
def summary(request: Request, session: db_session, _: reader, accounts: scope, store_id: str = ""):
    return success_response(
        request, data=ClearanceService(session).summary(accounts, store_id), meta=None
    )


@router.get("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def rules(
    request: Request, source_account_ref: str, session: db_session, _: reader, accounts: scope
):
    if source_account_ref not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    config, version = ClearanceService(session).repo.rules(source_account_ref)
    return success_response(
        request,
        data={"source_account_ref": source_account_ref, "version": version, "rules": config},
        meta=None,
    )


@router.put("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def put_rules(
    request: Request,
    payload: RuleWrite,
    session: db_session,
    principal: configurer,
    accounts: scope,
):
    return success_response(
        request,
        data=ClearanceService(session).update_rules(payload, accounts, principal.user_id),
        meta=None,
    )


@router.get("/requests", response_model=SuccessEnvelope[dict[str, Any], None])
def requests(
    request: Request,
    session: db_session,
    _: reader,
    accounts: scope,
    status: str | None = None,
    store_id: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    data = ClearanceService(session).list_requests(
        accounts, status=status, store_id=store_id, page=page, page_size=page_size
    )
    return success_response(request, data=data, meta=None)


@router.post("/requests", response_model=SuccessEnvelope[dict[str, Any], None])
def apply(
    request: Request,
    payload: ApplicationWrite,
    session: db_session,
    principal: applicant,
    accounts: scope,
):
    return success_response(
        request,
        data=ClearanceService(session).submit(payload, accounts, principal.user_id),
        meta=None,
    )


@router.get("/requests/{request_id}", response_model=SuccessEnvelope[dict[str, Any], None])
def request_detail(
    request: Request, request_id: UUID, session: db_session, _: reader, accounts: scope
):
    return success_response(
        request, data=ClearanceService(session).request_detail(request_id, accounts), meta=None
    )


@router.post(
    "/requests/{request_id}/withdraw", response_model=SuccessEnvelope[dict[str, Any], None]
)
def withdraw(
    request: Request, request_id: UUID, session: db_session, principal: applicant, accounts: scope
):
    return success_response(
        request,
        data=ClearanceService(session).withdraw(request_id, accounts, principal.user_id),
        meta=None,
    )


@router.put("/requests/{request_id}/progress", response_model=SuccessEnvelope[dict[str, Any], None])
def progress(
    request: Request,
    request_id: UUID,
    payload: ProgressWrite,
    session: db_session,
    principal: operator,
    accounts: scope,
):
    return success_response(
        request,
        data=ClearanceService(session).progress(request_id, payload, accounts, principal.user_id),
        meta=None,
    )


@router.post("/requests/{request_id}/pause", response_model=SuccessEnvelope[dict[str, Any], None])
def pause(
    request: Request, request_id: UUID, session: db_session, principal: operator, accounts: scope
):
    return success_response(
        request,
        data=ClearanceService(session).set_pause(request_id, accounts, principal.user_id, True),
        meta=None,
    )


@router.post("/requests/{request_id}/resume", response_model=SuccessEnvelope[dict[str, Any], None])
def resume(
    request: Request, request_id: UUID, session: db_session, principal: operator, accounts: scope
):
    return success_response(
        request,
        data=ClearanceService(session).set_pause(request_id, accounts, principal.user_id, False),
        meta=None,
    )


@router.get("/listings/{listing_id}", response_model=SuccessEnvelope[dict[str, Any], None])
def listing_detail(
    request: Request, listing_id: UUID, session: db_session, _: reader, accounts: scope
):
    return success_response(
        request, data=ClearanceService(session).listing_detail(str(listing_id), accounts), meta=None
    )


@router.get("/data-readiness", response_model=SuccessEnvelope[dict[str, Any], None])
def data_readiness(
    request: Request, session: db_session, _: reader, accounts: scope, store_id: str = ""
):
    rows = ClearanceService(session).list_listings(
        accounts, store_id=store_id, page=1, page_size=100000000
    )
    result = {
        "total": rows["total"],
        "missing_sales_window": 0,
        "missing_wfs_stock": 0,
        "missing_profit_cost": 0,
        "missing_listing_start": 0,
        "history_21day_eligible": 0,
    }
    for item in rows["items"]:
        eval_ = item["evaluation"]
        warnings = eval_["warnings"]
        result["missing_sales_window"] += int("SALES_WINDOW_UNVERIFIED" in warnings)
        result["missing_wfs_stock"] += int("WFS_STOCK_UNAVAILABLE_OR_STALE" in warnings)
        result["missing_profit_cost"] += int("PROFIT_COST_INCOMPLETE" in warnings)
        result["missing_listing_start"] += int("LISTING_START_UNKNOWN" in warnings)
        result["history_21day_eligible"] += int(eval_["positive_stock_days_30d"] >= 21)
    return success_response(request, data=result, meta=None)
