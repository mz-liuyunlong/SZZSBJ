"""Real WFS clearance API: scoped reads, governed requests and manual progress."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.clearance_center.field_access import mask_clearance_financials
from app.modules.clearance_center.schemas import (
    ApplicationWrite,
    ListingQuery,
    ProgressWrite,
    RuleWrite,
)
from app.modules.clearance_center.service import ClearanceService
from app.modules.data_pages.field_access import (
    ORDER_PROFIT_GROSS_PROFIT_PERMISSION,
    ORDER_PROFIT_MARGIN_PERMISSION,
)
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


def _requested_accounts(
    accounts: frozenset[str], source_account_ref: str = "",
) -> frozenset[str]:
    if not source_account_ref:
        return accounts
    if source_account_ref not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return frozenset({source_account_ref})


def _safe_listing(data: dict[str, Any], principal: Principal) -> dict[str, Any]:
    return mask_clearance_financials(
        data,
        can_view_profit=has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION),
        can_view_margin=has_permission(principal, ORDER_PROFIT_MARGIN_PERMISSION),
    )


@router.get("/listings", response_model=SuccessEnvelope[dict[str, Any], None])
def listings(
    request: Request,
    query: Annotated[ListingQuery, Query()],
    session: db_session,
    principal: reader,
    accounts: scope,
):
    if not has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION):
        # Filtering by a private profit-derived risk before redaction would
        # reveal the hidden classification through membership and totals.
        if query.risk_level is not None or query.candidate_status is not None:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    data = ClearanceService(session).list_listings(
        _requested_accounts(accounts, query.source_account_ref),
        store_id=query.store_id,
        keyword=query.keyword,
        risk_level=query.risk_level,
        candidate_status=query.candidate_status,
        page=query.page,
        page_size=query.page_size,
        financial_sort=has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION),
    )
    return success_response(request, data=_safe_listing(data, principal), meta=None)


@router.get("/eligible-listings", response_model=SuccessEnvelope[dict[str, Any], None])
def eligible_listings(
    request: Request,
    query: Annotated[ListingQuery, Query()],
    session: db_session,
    principal: applicant,
    accounts: scope,
):
    data = ClearanceService(session).list_listings(
        _requested_accounts(accounts, query.source_account_ref),
        store_id=query.store_id,
        keyword=query.keyword,
        eligible_only=True,
        page=query.page,
        page_size=query.page_size,
    )
    return success_response(request, data=_safe_listing(data, principal), meta=None)


@router.get("/facets", response_model=SuccessEnvelope[dict[str, Any], None])
def facets(request: Request, session: db_session, _: reader, accounts: scope):
    return success_response(
        request, data=ClearanceService(session).repo.facets(accounts), meta=None
    )


@router.get("/summary", response_model=SuccessEnvelope[dict[str, Any], None])
def summary(
    request: Request, session: db_session, principal: reader,
    accounts: scope, store_id: str = "", source_account_ref: str = "",
):
    result = ClearanceService(session).summary(
        _requested_accounts(accounts, source_account_ref), store_id
    )
    if not has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION):
        # Aggregate medium/observe/review counts may disclose hidden margin signals.
        for name in ("medium", "observe", "review_required"):
            result[name] = None
    return success_response(request, data=result, meta=None)


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
    source_account_ref: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    data = ClearanceService(session).list_requests(
        _requested_accounts(accounts, source_account_ref),
        status=status, store_id=store_id, page=page, page_size=page_size
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
    request: Request, request_id: UUID, session: db_session, principal: reader, accounts: scope
):
    return success_response(
        request,
        data=_safe_listing(
            ClearanceService(session).request_detail(request_id, accounts), principal
        ),
        meta=None,
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
    request: Request, listing_id: UUID, session: db_session, principal: reader, accounts: scope
):
    return success_response(
        request,
        data=_safe_listing(
            ClearanceService(session).listing_detail(str(listing_id), accounts), principal
        ),
        meta=None,
    )


@router.get("/data-readiness", response_model=SuccessEnvelope[dict[str, Any], None])
def data_readiness(
    request: Request,
    session: db_session,
    _: reader,
    accounts: scope,
    store_id: str = "",
    source_account_ref: str = "",
):
    report = ClearanceService(session).repo.readiness_report(
        _requested_accounts(accounts, source_account_ref), store_id=store_id
    )
    return success_response(request, data=report, meta=None)


@router.get("/daily-evaluation", response_model=SuccessEnvelope[dict[str, Any], None])
def daily_evaluation(
    request: Request,
    session: db_session,
    _: reader,
    accounts: scope,
    store_id: str = "",
    source_account_ref: str = "",
):
    # Only counts from authorized accounts, never global run statistics.
    report = ClearanceService(session).repo.readiness_report(
        _requested_accounts(accounts, source_account_ref), store_id=store_id
    )
    return success_response(
        request,
        data={
            "timezone": "America/Los_Angeles",
            "scheduled_local_time": "00:00",
            "as_of_policy": "previous_completed_LA_day",
            "runs_automatically": True,
            "evaluation_status": report["evaluation_status"],
            "scheduled_run_status": report["scheduled_run_status"],
            "scheduled_attempt_count": report["scheduled_attempt_count"],
            "scheduled_started_at": report["scheduled_started_at"],
            "scheduled_finished_at": report["scheduled_finished_at"],
            "scheduled_next_retry_at": report["scheduled_next_retry_at"],
            "scheduled_error_code": report["scheduled_error_code"],
            "expected_run_date_la": report["expected_run_date_la"],
            "run_date_la": report["run_date_la"],
            "as_of_date_la": report["as_of_date_la"],
            "evaluated_listings": report["evaluated_listings"],
            "not_evaluated_listings": report["not_evaluated_listings"],
        },
        meta=None,
    )
