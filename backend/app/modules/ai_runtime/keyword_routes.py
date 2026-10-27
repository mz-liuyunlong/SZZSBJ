"""Durable keyword task API. Existing keyword result contract remains untouched."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from io import BytesIO
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.celery_app import AI_QUEUE
from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session, get_session_factory
from app.modules.ai_runtime.four_sheet_export import generate_four_sheet_review
from app.modules.ai_runtime.provider import (
    AIUnavailable,
    select_active_connector,
    select_published_skill,
)
from app.modules.ai_runtime.v1_bulk_workbook import (
    V1ConfirmedConfig,
    create_v1_workbook,
    read_review_primary_sheet,
)
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.keyword_planning.analysis_routes import CreateRunRequest, _require_opted_in_writes
from app.modules.keyword_planning.internal_export import HEADERS_01
from app.modules.keyword_planning.models import AiKwAnalysisRun, AiKwRunKeyword, DimKwTerm

router = APIRouter(prefix="/ai-tasks", tags=["AI keyword jobs"])


class JobResponse(BaseModel):
    id: UUID
    source_account_ref: str
    product_id: UUID
    requested_by: str
    status: str
    phase: str
    progress: int
    total: int
    completed: int
    failed: int
    run_id: UUID | None
    error_code: str | None


class JobList(BaseModel):
    items: list[JobResponse]
    total: int


scope_dep = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_perm = Annotated[Principal, Depends(require_permission("page:ai-center:keyword-launch:view"))]
write_perm = Annotated[
    Principal, Depends(require_permission("action:ai-center:keyword-launch:manage"))
]


def _check(account: str, accounts: frozenset[str], principal: Principal) -> None:
    if principal.user_id == PREVIEW_PRINCIPAL_ID or account not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def _assert_job_owner(requested_by: str, principal: Principal) -> None:
    if requested_by != principal.user_id and not has_permission(principal, "business-rules:write"):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)


def _job(session: Session, job_id: UUID, account: str, principal: Principal):
    row = (
        session.execute(
            text("SELECT * FROM ai_runtime_jobs WHERE id=:id AND source_account_ref=:account"),
            {"id": job_id, "account": account},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    _assert_job_owner(row["requested_by"], principal)
    return row


def _read(row) -> JobResponse:
    return JobResponse.model_validate({k: row[k] for k in JobResponse.model_fields})


@router.post("", response_model=SuccessEnvelope[JobResponse, None])
def create_keyword_ai_job(
    request: Request,
    body: CreateRunRequest,
    accounts: scope_dep,
    principal: write_perm,
):
    _check(body.source_account_ref, accounts, principal)
    _require_opted_in_writes()
    payload = body.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    # The source-account dependency already queried its own Session; use a new
    # transaction so SQLAlchemy autobegin cannot conflict with our advisory lock.
    with get_session_factory()() as session, session.begin():
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": body.source_account_ref + ":" + body.request_key},
        )
        existing = (
            session.execute(
                text(
                    "SELECT * FROM ai_runtime_jobs WHERE source_account_ref=:a AND request_key=:k"
                ),
                {"a": body.source_account_ref, "k": body.request_key},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            _assert_job_owner(existing["requested_by"], principal)
            stored = {k: existing["input_json"].get(k) for k in payload}
            if hashlib.sha256(json.dumps(stored, sort_keys=True).encode()).hexdigest() != digest:
                raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
            data = _read(existing)
        else:
            try:
                connector = select_active_connector(session, "keyword_launch")
            except AIUnavailable as exc:
                raise ApiError(code=exc.code, status_code=409) from None
            skill = select_published_skill(session, connector["id"], "keyword_launch")
            payload["connector_id"] = str(connector["id"])
            payload["skill_version_id"] = str(skill["id"]) if skill else None
            job_id = uuid4()
            session.execute(
                text("""INSERT INTO ai_runtime_jobs(id,source_account_ref,product_id,requested_by,request_key,input_json)
              VALUES (:id,:account,:product,:actor,:key,CAST(:input AS jsonb))"""),
                {
                    "id": job_id,
                    "account": body.source_account_ref,
                    "product": body.product_id,
                    "actor": principal.user_id,
                    "key": body.request_key,
                    "input": json.dumps(payload),
                },
            )
            row = (
                session.execute(text("SELECT * FROM ai_runtime_jobs WHERE id=:id"), {"id": job_id})
                .mappings()
                .one()
            )
            data = _read(row)
    if data.status == "queued":
        from app.modules.ai_runtime.tasks import execute_keyword_ai_job

        try:
            execute_keyword_ai_job.apply_async(
                args=[str(data.id)], queue=AI_QUEUE, routing_key=AI_QUEUE
            )
        except Exception:
            # Database is the source of truth; recovery dispatcher will retry.
            pass
    return success_response(request, data=data)


@router.get("", response_model=SuccessEnvelope[JobList, None])
def list_keyword_ai_jobs(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: read_perm,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    _check(source_account_ref, accounts, principal)
    rows = (
        session.execute(
            text("""SELECT * FROM ai_runtime_jobs WHERE source_account_ref=:account
      AND (requested_by=:actor OR :manager) ORDER BY created_at DESC LIMIT :lim"""),
            {
                "account": source_account_ref,
                "actor": principal.user_id,
                "manager": has_permission(principal, "business-rules:write"),
                "lim": limit,
            },
        )
        .mappings()
        .all()
    )
    return success_response(request, data=JobList(items=[_read(x) for x in rows], total=len(rows)))


@router.get("/{job_id}", response_model=SuccessEnvelope[JobResponse, None])
def get_keyword_ai_job(
    job_id: UUID,
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: read_perm,
):
    _check(source_account_ref, accounts, principal)
    return success_response(
        request, data=_read(_job(session, job_id, source_account_ref, principal))
    )


@router.post("/{job_id}/cancel", response_model=SuccessEnvelope[JobResponse, None])
def cancel_keyword_ai_job(
    job_id: UUID,
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: write_perm,
):
    _check(source_account_ref, accounts, principal)
    _require_opted_in_writes()
    _job(session, job_id, source_account_ref, principal)
    session.execute(
        text("""UPDATE ai_runtime_jobs SET status='cancelled',phase='cancelled',finished_at=now()
      WHERE id=:id AND status IN ('queued','running')"""),
        {"id": job_id},
    )
    session.commit()
    return success_response(
        request, data=_read(_job(session, job_id, source_account_ref, principal))
    )


@router.post("/{job_id}/retry", response_model=SuccessEnvelope[JobResponse, None])
def retry_keyword_ai_job(
    job_id: UUID,
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: write_perm,
):
    _check(source_account_ref, accounts, principal)
    _require_opted_in_writes()
    row = _job(session, job_id, source_account_ref, principal)
    if row["status"] not in ("failed", "partial_success"):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    session.execute(
        text("""UPDATE ai_runtime_jobs SET status='queued',phase='queued',error_code=NULL,
      started_at=NULL,finished_at=NULL,lease_until=NULL,progress=0,failed=0,
      completed=0 WHERE id=:id"""),
        {"id": job_id},
    )
    session.commit()
    from app.modules.ai_runtime.tasks import execute_keyword_ai_job

    try:
        execute_keyword_ai_job.apply_async(args=[str(job_id)], queue=AI_QUEUE, routing_key=AI_QUEUE)
    except Exception:
        pass
    return success_response(
        request, data=_read(_job(session, job_id, source_account_ref, principal))
    )


@router.get("/{job_id}/results")
def get_keyword_ai_suggestions(
    job_id: UUID,
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: read_perm,
):
    """Show AI-sidecar recommendations without changing the immutable V1.1 decisions."""
    _check(source_account_ref, accounts, principal)
    _job(session, job_id, source_account_ref, principal)
    batches = (
        session.execute(
            text(
                """SELECT output_json FROM ai_runtime_results
            WHERE job_id=:id AND status='succeeded' ORDER BY batch_index"""
            ),
            {"id": job_id},
        )
        .scalars()
        .all()
    )
    items = []
    for batch in batches:
        if isinstance(batch, dict) and isinstance(batch.get("items"), list):
            items.extend(
                {
                    "keyword": x.get("keyword"),
                    "relevance": x.get("relevance"),
                    "risk": x.get("risk"),
                    "reason": x.get("reason"),
                }
                for x in batch["items"]
                if isinstance(x, dict)
            )
    return success_response(
        request, data={"items": items, "total": len(items), "advisory_only": True}
    )


@router.get("/{job_id}/four-sheet-workbook")
def download_keyword_ai_four_sheet(
    job_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: read_perm,
) -> StreamingResponse:
    """Four-sheet INTERNAL review from the run bound to an authorized AI job."""
    _check(source_account_ref, accounts, principal)
    job = _job(session, job_id, source_account_ref, principal)
    if job["status"] not in ("succeeded", "partial_success") or not job["run_id"]:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    run = session.scalar(
        select(AiKwAnalysisRun).where(
            AiKwAnalysisRun.id == job["run_id"],
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
                AiKwRunKeyword.run_id == run.id,
                AiKwRunKeyword.source_account_ref == source_account_ref,
            )
            .order_by(AiKwRunKeyword.rank_index.asc().nulls_last(), AiKwRunKeyword.term_id.asc())
            .limit(20001)
        )
    )
    if len(rows) > 20000:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    batches = (
        session.execute(
            text("""SELECT output_json FROM ai_runtime_results
        WHERE job_id=:job AND status='succeeded' ORDER BY batch_index"""),
            {"job": job_id},
        )
        .scalars()
        .all()
    )
    ai_items = [
        item
        for batch in batches
        if isinstance(batch, dict)
        for item in batch.get("items", [])
        if isinstance(item, dict)
    ]
    draft = session.execute(
        text("""SELECT output_json FROM ai_runtime_results
        WHERE job_id=:job AND batch_index=-1 AND status='succeeded'"""),
        {"job": job_id},
    ).scalar_one_or_none()
    try:
        content = generate_four_sheet_review(
            run=run,
            keyword_rows=rows,
            ai_items=ai_items,
            listing_draft=draft if isinstance(draft, dict) else None,
        )
    except ValueError:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409) from None
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="kw_ai_review_{job_id}.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


class V1GenerateRequest(BaseModel):
    source_account_ref: str
    sku: str
    owner_initials: str
    confirmation: str
    template_version: str
    start_date: str | None = None
    manual_bid: Decimal = Decimal("0.31")
    auto_bid: Decimal = Decimal("0.21")
    manual_budget: Decimal = Decimal("10")
    auto_budget: Decimal = Decimal("10")


@router.post("/{job_id}/v1-workbook")
def download_confirmed_v1_workbook(
    job_id: UUID,
    body: V1GenerateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    accounts: scope_dep,
    principal: read_perm,
) -> StreamingResponse:
    """Confirmed five-sheet V1.0 export, no external Walmart write."""
    _check(body.source_account_ref, accounts, principal)
    job = _job(session, job_id, body.source_account_ref, principal)
    if job["status"] != "succeeded" or not job["run_id"]:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    run = session.scalar(
        select(AiKwAnalysisRun).where(
            AiKwAnalysisRun.id == job["run_id"],
            AiKwAnalysisRun.source_account_ref == body.source_account_ref,
            AiKwAnalysisRun.status == "succeeded",
        )
    )
    if run is None:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    verified = session.execute(
        text("""SELECT
            (SELECT status FROM ai_kw_product_fact_snapshot
              WHERE id=:fact AND source_account_ref=:account),
            (SELECT status FROM ai_kw_rule_version WHERE id=:rule)"""),
        {
            "fact": run.product_fact_snapshot_id,
            "account": body.source_account_ref,
            "rule": run.rule_version_id,
        },
    ).one()
    if verified != ("confirmed", "published"):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    if body.confirmation != "确认无误，开始生成" or body.template_version != "V1-24":
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
    rows = list(
        session.execute(
            select(AiKwRunKeyword, DimKwTerm.canonical_keyword)
            .join(DimKwTerm, DimKwTerm.id == AiKwRunKeyword.term_id)
            .where(
                AiKwRunKeyword.run_id == run.id,
                AiKwRunKeyword.source_account_ref == body.source_account_ref,
            )
            .order_by(AiKwRunKeyword.rank_index.asc().nulls_last(), AiKwRunKeyword.term_id.asc())
            .limit(20001)
        )
    )
    if not rows or len(rows) > 20000:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    batches = (
        session.execute(
            text("""SELECT output_json FROM ai_runtime_results
                 WHERE job_id=:job AND batch_index>=0
                   AND status='succeeded' ORDER BY batch_index"""),
            {"job": job_id},
        )
        .scalars()
        .all()
    )
    ai_items = [
        item
        for batch in batches
        if isinstance(batch, dict)
        for item in batch.get("items", [])
        if isinstance(item, dict)
    ]
    metadata = {
        keyword.casefold(): {
            "broad_role": row.broad_role,
            "root_grade": row.root_grade,
            "broad_reason": row.broad_reason,
            "risk_reasons": row.risk_reasons_json,
        }
        for row, keyword in rows
    }
    listing_draft = session.execute(
        text("""SELECT output_json FROM ai_runtime_results
        WHERE job_id=:job AND batch_index=-1 AND status='succeeded'"""),
        {"job": job_id},
    ).scalar_one_or_none()
    try:
        reviewed = generate_four_sheet_review(run=run, keyword_rows=rows, ai_items=ai_items)
        source_rows = read_review_primary_sheet(reviewed)
        cfg = V1ConfirmedConfig(
            item_id=run.item_id,
            sku=body.sku,
            owner_initials=body.owner_initials,
            product_facts_confirmed=True,
            rule_version_published=True,
            user_confirmed_generation=True,
            walmart_template_verified=True,
            start_date=body.start_date,
            manual_bid=body.manual_bid,
            auto_bid=body.auto_bid,
            manual_budget=body.manual_budget,
            auto_budget=body.auto_budget,
        )
        content = create_v1_workbook(
            tuple(HEADERS_01),
            source_rows,
            cfg,
            metadata=metadata,
            listing_draft=listing_draft if isinstance(listing_draft, dict) else None,
        )
    except (ValueError, KeyError, TypeError):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409) from None
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="kw_v1_{job_id}.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
