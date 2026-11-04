"""Feishu encrypted organization callback, isolated from ordinary user authentication.

The callback has no RBAC principal. Its only trust boundary is a valid timestamped
Feishu signature, AES-encrypted payload, verification token and app_id check.
Both receiver and worker remain disabled unless explicitly enabled.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, success_response
from app.core.config import get_settings
from app.core.auth import Principal
from app.core.permissions import require_super_admin
from app.db.session import get_db_session
from app.db.session import get_session_factory
from app.modules.iam.organization_event_inbox import (
    enqueue_contact_event,
    revoke_linked_sessions,
)
from app.modules.iam.organization_events import decode_feishu_event

router = APIRouter(tags=["iam-organization-events"])
admin_principal = Annotated[Principal, Depends(require_super_admin)]
db_session = Annotated[Session, Depends(get_db_session)]


class RetryOrganizationEventsRequest(BaseModel):
    event_ids: list[str] = Field(min_length=1, max_length=50)
    confirmation: str



@router.post("/api/integrations/feishu/organization-events")
async def receive_organization_event(request: Request):
    settings = get_settings()
    if not settings.feishu_org_events_enabled:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    # Bound memory before decoding any untrusted input.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64 * 1024:
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=413)

    encrypt_secret = settings.feishu_org_event_encrypt_key
    verification_secret = settings.feishu_org_event_verification_token
    if not encrypt_secret or not verification_secret or not settings.feishu_app_id:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    decoded = decode_feishu_event(
        raw_body=bytes(body),
        timestamp=request.headers.get("X-Lark-Request-Timestamp", ""),
        nonce=request.headers.get("X-Lark-Request-Nonce", ""),
        signature=request.headers.get("X-Lark-Signature", ""),
        encrypt_key=encrypt_secret.get_secret_value(),
        verification_token=verification_secret.get_secret_value(),
        app_id=settings.feishu_app_id,
    )
    if decoded.challenge is not None:
        return {"challenge": decoded.challenge}
    if decoded.event is None:
        return success_response(request, data={"accepted": False}, meta=None)

    event = decoded.event
    with get_session_factory()() as session:
        session: Session
        inserted = enqueue_contact_event(session, event)
        if inserted and event.revoke_session and event.open_id:
            revoke_linked_sessions(session, event.open_id)
        session.commit()

    return success_response(request, data={"accepted": True}, meta=None)


@router.get("/api/settings/organization/event-inbox")
def list_organization_event_inbox(
    request: Request,
    _: admin_principal,
    session: db_session,
    status: str | None = None,
):
    """Read-only bounded operational view; no raw event content is exposed."""
    if status and status not in {
        "pending", "processing", "retry", "needs_review", "applied"
    }:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    rows = session.execute(
        text(
            """
            SELECT event_id, event_type, status, attempt_count,
                   received_at, updated_at, processed_at, last_error_code,
                   last_run_id
            FROM iam_feishu_org_events
            WHERE (:status IS NULL OR status = :status)
            ORDER BY received_at DESC, event_id DESC
            LIMIT 100
            """
        ),
        {"status": status},
    ).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.post("/api/settings/organization/event-inbox/retry")
def retry_organization_events(
    request: Request,
    payload: RetryOrganizationEventsRequest,
    _: admin_principal,
    session: db_session,
):
    """Explicitly release selected review events for one more safe reconciliation."""
    if payload.confirmation != "确认重新执行飞书组织核对":
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    if len(set(payload.event_ids)) != len(payload.event_ids):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    updated = session.execute(
        text(
            """
            UPDATE iam_feishu_org_events
            SET status = 'pending', next_attempt_at = now(),
                attempt_count = 0, last_error_code = NULL, updated_at = now()
            WHERE event_id = ANY(:event_ids) AND status = 'needs_review'
            RETURNING event_id
            """
        ),
        {"event_ids": payload.event_ids},
    ).scalars()
    updated_ids = sorted(str(value) for value in updated)
    if len(updated_ids) != len(payload.event_ids):
        session.rollback()
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    session.commit()
    return success_response(request, data={"queued": len(updated_ids)}, meta=None)
