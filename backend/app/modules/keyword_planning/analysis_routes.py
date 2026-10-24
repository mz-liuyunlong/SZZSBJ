"""Authenticated source-derived runs and INTERNAL-only five-sheet download.

No arbitrary user-supplied scores, rules or keywords; no Walmart write actions.
POST is protected by the repository's scoped-write guard and products:write RBAC.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

from .analysis_entrypoint import create_analysis_from_stored_sources
from .analysis_execution import AnalysisBlocked
from .internal_export import generate_internal_workbook
from .models import AiKwAnalysisRun, AiKwProductFactSnapshot, AiKwRunKeyword, DimKwTerm
from .upload_persistence import PrivateLocalKeywordStore, persist_original_keyword_upload
from .workbook_ingestion import MAX_FILE_BYTES, WorkbookRejected

router = APIRouter(tags=["Keyword Planning"])


class CreateRunRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    product_id: UUID
    item_id: str = Field(min_length=1, max_length=128)
    product_fact_snapshot_id: UUID
    rule_version_id: UUID
    upload_file_id: UUID
    request_key: str = Field(min_length=1, max_length=255)


class UploadRead(BaseModel):
    upload_id: UUID
    status: str
    source_rows: int


class CreateRunRead(BaseModel):
    run_id: UUID
    status: str
    created: bool
    keyword_count: int
    official_export_authorized: bool = False


def _account_allowed(account: str, allowed: frozenset[str], principal: Principal) -> None:
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    if not account.strip() or account not in allowed:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def _require_opted_in_writes() -> None:
    if os.environ.get("KEYWORD_V11_WRITE_ENABLED") != "1":
        raise ApiError(
            code=ErrorCode.FORBIDDEN,
            status_code=403,
            details={"reason_code": "KEYWORD_WRITES_DISABLED"},
        )


@router.post("/imports/xlsx", response_model=SuccessEnvelope[UploadRead, None])
async def upload_keyword_xlsx(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    product_id: UUID,
    product_fact_snapshot_id: UUID,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
) -> SuccessEnvelope[UploadRead, None]:
    _account_allowed(source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    root = os.environ.get("SZZSBJ_KEYWORD_PRIVATE_ROOT")
    if not root:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "PRIVATE_STORAGE_NOT_CONFIGURED"},
        )
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=413,
                details={"reason_code": "UPLOAD_TOO_LARGE"},
            )
        chunks.append(chunk)
    # A source-account grant alone does not establish permission over a global product ID.
    # Require a frozen confirmed product fact anchored to the same account/product.
    owned_fact = session.scalar(
        select(AiKwProductFactSnapshot).where(
            AiKwProductFactSnapshot.id == product_fact_snapshot_id,
            AiKwProductFactSnapshot.source_account_ref == source_account_ref,
            AiKwProductFactSnapshot.product_id == product_id,
            AiKwProductFactSnapshot.status == "confirmed",
            AiKwProductFactSnapshot.item_verified.is_(True),
        )
    )
    if owned_fact is None:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    session.rollback()
    try:
        store = PrivateLocalKeywordStore(Path(root))
        upload_id, status, total = persist_original_keyword_upload(
            session,
            account=source_account_ref,
            product_id=product_id,
            filename=filename,
            actor=principal.user_id,
            raw_blob=b"".join(chunks),
            store=store,
        )
    except (ValueError, WorkbookRejected) as exc:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
        ) from exc
    return success_response(
        request,
        data=UploadRead(
            upload_id=upload_id,
            status=status,
            source_rows=total,
        ),
        meta=None,
    )


@router.post("/analyses", response_model=SuccessEnvelope[CreateRunRead, None])
def create_analysis(
    request: Request,
    body: CreateRunRequest,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
) -> SuccessEnvelope[CreateRunRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    try:
        receipt = create_analysis_from_stored_sources(
            session,
            account=body.source_account_ref,
            product_id=body.product_id,
            item_id=body.item_id,
            fact_id=body.product_fact_snapshot_id,
            rule_version_id=body.rule_version_id,
            upload_id=body.upload_file_id,
            request_key=body.request_key,
            actor=principal.user_id,
        )
    except AnalysisBlocked as exc:
        # Stable machine-readable code, never raw payload or secrets.
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
        ) from exc
    return success_response(
        request,
        data=CreateRunRead(
            run_id=receipt.run_id,
            status=receipt.status,
            created=receipt.created,
            keyword_count=receipt.keyword_count,
        ),
        meta=None,
    )


@router.get("/runs/{run_id}/internal-workbook")
def download_internal_workbook(
    run_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
) -> StreamingResponse:
    _account_allowed(source_account_ref, allowed_accounts, principal)
    run = session.scalar(
        select(AiKwAnalysisRun).where(
            AiKwAnalysisRun.id == run_id,
            AiKwAnalysisRun.source_account_ref == source_account_ref,
        )
    )
    if run is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    rows = list(
        session.execute(
            select(AiKwRunKeyword, DimKwTerm.canonical_keyword)
            .join(DimKwTerm, DimKwTerm.id == AiKwRunKeyword.term_id)
            .where(
                AiKwRunKeyword.run_id == run_id,
                AiKwRunKeyword.source_account_ref == source_account_ref,
            )
            .order_by(AiKwRunKeyword.rank_index.asc().nulls_last(), AiKwRunKeyword.term_id.asc())
            .limit(20001)
        )
    )
    if len(rows) > 20000:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "WORKBOOK_TOO_LARGE"},
        )
    try:
        content = generate_internal_workbook(run=run, keyword_rows=rows)
    except ValueError as exc:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
        ) from exc
    return StreamingResponse(
        BytesIO(content),
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f'attachment; filename="kw_internal_{run_id}.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
