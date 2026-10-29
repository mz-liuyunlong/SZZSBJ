"""Store-scoped task API; never exposes Walmart credentials or raw payloads."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.integrations.walmart.remote_dispatch import ALLOWED_KEYS, STORES, parse_routes
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.walmart_remote.models import WalmartRemoteJob
from app.modules.walmart_remote.tasks import dispatch_remote_job
from app.modules.walmart_scf.store_scope import verify_http_store
from app.modules.walmart_scf.unified import store_code_for

router = APIRouter(prefix="/api/integrations/walmart-remote", tags=["Walmart Remote"])
db = Annotated[Session, Depends(get_db_session)]
scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
reader = Annotated[Principal, Depends(require_permission("integrations:read"))]
executor = Annotated[Principal, Depends(require_permission("integrations:execute"))]


class CreateJob(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    request_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    operations: list[str] = Field(min_length=1, max_length=4)


class JobView(BaseModel):
    id: UUID
    source_account_ref: str
    store_id: str
    store_code: str
    operations: list[str]
    status: str
    run_id: str | None
    files_verified: int | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def job_view(item: WalmartRemoteJob) -> JobView:
    return JobView.model_validate({
        name: getattr(item, name)
        for name in JobView.model_fields
    })


@router.post(
    "/jobs",
    response_model=SuccessEnvelope[JobView, None],
    responses={403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
def create_job(
    payload: CreateJob,
    request: Request,
    session: db,
    principal: executor,
    account_scope: scope,
) -> SuccessEnvelope[JobView, None]:
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        raise ApiError(code="REMOTE_COLLECTION_DISABLED", status_code=503)
    store = store_code_for(payload.store_id)
    verify_http_store(
        principal=principal,
        session=session,
        source_account_ref=payload.source_account_ref,
        store_id=payload.store_id,
        verified_source_account_scope=account_scope,
        store_code=store,
    )
    try:
        routes = parse_routes(os.getenv("SZZSBJ_WALMART_REMOTE_ROUTES", ""))
        allowed = frozenset(
            part.strip()
            for part in os.getenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", "").split(",")
            if part.strip()
        )
    except Exception:
        raise ApiError(code="REMOTE_ROUTES_UNAVAILABLE", status_code=503) from None
    if store not in routes or store not in allowed or not allowed <= STORES:
        raise ApiError(code="REMOTE_STORE_DISABLED", status_code=503)
    if len(set(payload.operations)) != len(payload.operations):
        raise ApiError(code="REMOTE_OPERATION_INVALID", status_code=422)
    if not set(payload.operations) <= ALLOWED_KEYS:
        raise ApiError(code="REMOTE_OPERATION_INVALID", status_code=422)
    current = session.scalar(
        select(WalmartRemoteJob).where(
            WalmartRemoteJob.source_account_ref == payload.source_account_ref,
            WalmartRemoteJob.store_id == payload.store_id,
            WalmartRemoteJob.request_key == payload.request_key,
        )
    )
    if current is not None:
        if current.operations != payload.operations:
            raise ApiError(code="REMOTE_JOB_CONFLICT", status_code=409)
        return success_response(request, data=job_view(current))
    job = WalmartRemoteJob(
        id=uuid4(),
        source_account_ref=payload.source_account_ref,
        store_id=payload.store_id,
        store_code=store,
        request_key=payload.request_key,
        operations=payload.operations,
        requested_by=principal.user_id,
        status="queued",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    try:
        dispatch_remote_job(job.id)
    except Exception:
        # Reconcile manually; do not auto-dispatch a duplicate job.
        raise ApiError(code="REMOTE_DISPATCH_UNAVAILABLE", status_code=503) from None
    return success_response(request, data=job_view(job))


@router.get(
    "/jobs/{job_id}",
    response_model=SuccessEnvelope[JobView, None],
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def get_job(
    job_id: UUID,
    request: Request,
    session: db,
    principal: reader,
    account_scope: scope,
) -> SuccessEnvelope[JobView, None]:
    item = session.get(WalmartRemoteJob, job_id)
    if item is None:
        raise ApiError(code="REMOTE_JOB_NOT_FOUND", status_code=404)
    store = store_code_for(item.store_id)
    verify_http_store(
        principal=principal,
        session=session,
        source_account_ref=item.source_account_ref,
        store_id=item.store_id,
        verified_source_account_scope=account_scope,
        store_code=store,
    )
    return success_response(request, data=job_view(item))
