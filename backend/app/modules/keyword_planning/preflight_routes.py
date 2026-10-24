"""FastAPI source-scoped preflight; no external fetch, scoring or database mutations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

from .analysis_preflight import inspect_readiness
from .analysis_routes import _account_allowed

router = APIRouter(tags=["Keyword Planning"])


class PreflightRead(BaseModel):
    can_create_review_run: bool
    can_generate_scored_results: bool
    can_generate_official_upload: bool
    candidate_count: int
    automatic_evidence_count: int
    reviewed_evidence_count: int
    manual_review_count: int
    top40_review_required: int
    review_reason_codes: tuple[str, ...]
    source_account_ref: str
    product_id: UUID
    rule_version_id: UUID


@router.get("/preflight", response_model=SuccessEnvelope[PreflightRead, None])
def inspect_analysis_preflight(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    product_id: UUID,
    item_id: str,
    product_fact_snapshot_id: UUID,
    rule_version_id: UUID,
    upload_file_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
    selected_asins: Annotated[list[str] | None, Query()] = None,
):
    _account_allowed(source_account_ref, allowed_accounts, principal)
    if not item_id or len(item_id) > 128:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
    result = inspect_readiness(
        session,
        account=source_account_ref,
        product_id=product_id,
        item_id=item_id,
        fact_id=product_fact_snapshot_id,
        rule_version_id=rule_version_id,
        upload_id=upload_file_id,
        actor=principal.user_id,
        selected_asins=tuple(selected_asins) if selected_asins is not None else None,
    )
    return success_response(
        request,
        data=PreflightRead(
            can_create_review_run=result.can_create_review_run,
            can_generate_scored_results=result.can_generate_scored_results,
            can_generate_official_upload=result.can_generate_official_upload,
            candidate_count=result.candidate_count,
            automatic_evidence_count=result.automatic_evidence_count,
            reviewed_evidence_count=result.reviewed_evidence_count,
            manual_review_count=result.manual_review_count,
            top40_review_required=result.top40_review_required,
            review_reason_codes=result.review_reason_codes,
            source_account_ref=result.source_account_ref,
            product_id=result.product_id,
            rule_version_id=result.rule_version_id,
        ),
        meta=None,
    )
