"""Explicitly gated read-only Listing evidence preview."""

from __future__ import annotations

from datetime import date, datetime, timedelta, UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.permissions import require_permission
from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.listing_rule_config.preview import (
    ListingEvaluationPreview,
    ListingEvaluationPreviewService,
)
from app.modules.listing_rule_config.evaluation import rating_cutoff_la

router = APIRouter(prefix="/api/listings", tags=["Listing Evaluation Preview"])
DB = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view = Depends(require_permission("page:products:listing-management:view"))


@router.get(
    "/evaluation-preview",
    response_model=SuccessEnvelope[ListingEvaluationPreview, dict[str, str]],
    responses={
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
    dependencies=[view],
)
def get_evaluation_preview(
    request: Request,
    session: DB,
    account_refs: scope,
    listing_id: UUID,
    cutoff_la: Annotated[date | None, Query()] = None,
):
    """Never run against a production DB without a separately enabled flag."""
    if not get_settings().listing_evaluation_preview_enabled:
        raise ApiError(
            code="LISTING_EVALUATION_PREVIEW_DISABLED",
            status_code=503,
            message="真实数据试算尚未授权启用",
        )
    latest = rating_cutoff_la(datetime.now(UTC))
    cutoff = cutoff_la or latest
    if cutoff > latest or cutoff < latest - timedelta(days=45):
        raise ApiError(
            code="LISTING_EVALUATION_CUTOFF_OUT_OF_RANGE",
            status_code=422,
            message="仅允许查询最近45天以内的已结束LA业务日期",
        )
    data = ListingEvaluationPreviewService(session).evaluate(
        listing_id=listing_id, account_refs=account_refs, cutoff=cutoff
    )
    return success_response(request, data=data, meta={"source": "read_only_diagnostic"})
