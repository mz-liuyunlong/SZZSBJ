"""Feishu encrypted organization callback, isolated from ordinary user authentication.

The callback has no RBAC principal. Its only trust boundary is a valid timestamped
Feishu signature, AES-encrypted payload, verification token and app_id check.
Both receiver and worker remain disabled unless explicitly enabled.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, success_response
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.iam.organization_event_inbox import (
    enqueue_contact_event,
    revoke_linked_sessions,
)
from app.modules.iam.organization_events import decode_feishu_event

router = APIRouter(tags=["iam-organization-events"])


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
