from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.ads_search_terms.schemas import (
    ActionComplete,
    ActionCreate,
    ActionListData,
    ActionRead,
    SearchTermListData,
    SearchTermQuery,
    SearchTermSummaryData,
    SearchTermTrendData,
)
from app.modules.ads_search_terms.service import AdsSearchTermsService
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(prefix="/api/ads/search-terms", tags=["Ads Search Terms"])
db = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
reader = Annotated[Principal, Depends(require_permission("ads.search_terms.view"))]
actor = Annotated[Principal, Depends(require_permission("ads.search_terms.actions.manage"))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def meta(
    *tables: str,
    total: int | None = None,
    freshness_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "source": "new_system_postgresql",
        "source_objects": list(tables),
        "total": total,
        "freshness_at": freshness_at,
    }


@router.get("", response_model=SuccessEnvelope[SearchTermListData, dict], responses=ERRORS)
def list_terms(
    request: Request,
    query: Annotated[SearchTermQuery, Query()],
    session: db,
    principal: reader,
    accounts: scope,
) -> SuccessEnvelope[SearchTermListData, dict]:
    del principal
    data = AdsSearchTermsService(session).list_terms(query, accounts)
    return success_response(
        request,
        data=data,
        meta=meta("fact_walmart_ad_search_term_daily", total=data.total),
    )


@router.get(
    "/summary",
    response_model=SuccessEnvelope[SearchTermSummaryData, dict],
    responses=ERRORS,
)
def summary(
    request: Request,
    query: Annotated[SearchTermQuery, Query()],
    session: db,
    principal: reader,
    accounts: scope,
) -> SuccessEnvelope[SearchTermSummaryData, dict]:
    del principal
    data = AdsSearchTermsService(session).summary(query, accounts)
    return success_response(
        request,
        data=data,
        meta=meta(
            "fact_walmart_ad_search_term_daily",
            "fact_walmart_keyword_sp_daily",
            freshness_at=data.freshness_at,
        ),
    )


@router.get(
    "/trends",
    response_model=SuccessEnvelope[SearchTermTrendData, dict],
    responses=ERRORS,
)
def trends(
    request: Request,
    session: db,
    principal: reader,
    accounts: scope,
    term: str = Query(min_length=1, max_length=256),
    start_date: date = Query(),
    end_date: date = Query(),
) -> SuccessEnvelope[SearchTermTrendData, dict]:
    del principal
    data = AdsSearchTermsService(session).trends(term, start_date, end_date, accounts)
    return success_response(
        request,
        data=data,
        meta=meta("fact_walmart_ad_search_term_daily"),
    )


@router.get(
    "/actions",
    response_model=SuccessEnvelope[ActionListData, dict],
    responses=ERRORS,
)
def actions(
    request: Request,
    session: db,
    principal: reader,
    accounts: scope,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> SuccessEnvelope[ActionListData, dict]:
    del principal
    data = AdsSearchTermsService(session).list_actions(accounts, page, page_size)
    return success_response(
        request,
        data=data,
        meta=meta("ops_ads_search_term_actions", total=data.total),
    )


@router.post(
    "/actions",
    status_code=201,
    response_model=SuccessEnvelope[ActionRead, dict],
    responses=ERRORS,
)
def create_action(
    request: Request,
    payload: ActionCreate,
    session: db,
    principal: actor,
    accounts: scope,
) -> SuccessEnvelope[ActionRead, dict]:
    data = AdsSearchTermsService(session).create_action(
        payload, str(principal.user_id), accounts
    )
    return success_response(
        request,
        data=data,
        meta=meta("ops_ads_search_term_actions"),
    )


@router.patch(
    "/actions/{action_id}/complete",
    response_model=SuccessEnvelope[ActionRead, dict],
    responses=ERRORS,
)
def complete_action(
    request: Request,
    action_id: UUID,
    payload: ActionComplete,
    session: db,
    principal: actor,
    accounts: scope,
) -> SuccessEnvelope[ActionRead, dict]:
    data = AdsSearchTermsService(session).complete_action(
        action_id,
        payload.completion_note,
        str(principal.user_id),
        accounts,
    )
    return success_response(
        request,
        data=data,
        meta=meta(
            "ops_ads_search_term_actions",
            "ops_ads_search_term_action_events",
        ),
    )
