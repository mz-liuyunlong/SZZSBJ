"""V1.1 read routes with separately gated review-only write subrouters."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

from .repository import KeywordPlanningRepository
from .schemas import KeywordListRead, RunListRead, RunRead
from .service import KeywordPlanningService

router = APIRouter(prefix="/api/v1/keyword-planning", tags=["Keyword Planning"])

session_dependency = Annotated[Session, Depends(get_db_session)]
account_scope_dependency = Annotated[frozenset[str], Depends(require_source_account_scope)]
principal_dependency = Annotated[
    Principal, Depends(require_permission("page:ai-center:keyword-launch:view"))
]


def get_service(
    session: session_dependency,
    allowed_accounts: account_scope_dependency,
    principal: principal_dependency,
) -> KeywordPlanningService:
    # Existing preview auth has broad legacy permissions. It must never read account-scoped
    # keyword decisions without an explicit future RBAC review, even if other endpoints allow it.
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    return KeywordPlanningService(KeywordPlanningRepository(session), allowed_accounts)


service_dependency = Annotated[KeywordPlanningService, Depends(get_service)]


@router.get("/products/{product_id}/runs", response_model=SuccessEnvelope[RunListRead, None])
def list_product_runs(
    request: Request,
    product_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    service: service_dependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessEnvelope[RunListRead, None]:
    return success_response(
        request,
        data=service.list_runs(
            product_id=product_id,
            account=source_account_ref,
            limit=limit,
            offset=offset,
        ),
        meta=None,
    )


@router.get("/runs/{run_id}", response_model=SuccessEnvelope[RunRead, None])
def get_analysis_run(
    request: Request,
    run_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    service: service_dependency,
) -> SuccessEnvelope[RunRead, None]:
    return success_response(
        request,
        data=service.get_run(run_id=run_id, account=source_account_ref),
        meta=None,
    )


@router.get("/runs/{run_id}/keywords", response_model=SuccessEnvelope[KeywordListRead, None])
def list_analysis_keywords(
    request: Request,
    run_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    service: service_dependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessEnvelope[KeywordListRead, None]:
    return success_response(
        request,
        data=service.list_keywords(
            run_id=run_id,
            account=source_account_ref,
            limit=limit,
            offset=offset,
        ),
        meta=None,
    )


# V1.1 write and INTERNAL review-only export routes; no advertising API execution.
from .analysis_routes import router as analysis_routes_router  # noqa: E402

router.include_router(analysis_routes_router)

# Safely scoped V1.1 preflight and scoring-rule governance extensions.
from .governance_routes import router as governance_routes_router  # noqa: E402
from .library_routes import router as library_routes_router  # noqa: E402
from .preflight_routes import router as preflight_routes_router  # noqa: E402
from .source_routes import router as source_routes_router  # noqa: E402

router.include_router(preflight_routes_router)
router.include_router(governance_routes_router)
router.include_router(source_routes_router)
router.include_router(library_routes_router)

from app.modules.ai_runtime.keyword_routes import router as keyword_ai_router  # noqa: E402

router.include_router(keyword_ai_router)
