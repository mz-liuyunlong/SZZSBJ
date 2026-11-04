"""Persistent sanitized 403 access-denial observability.

Only request IDs, route templates, principal identifier, canonical permission
keys, reason categories, status and timestamps are stored. Never persist URL
values, queries, headers, cookies, payloads, raw scope values or secrets.
Database observability failure cannot turn an authorization denial into 500.
"""

from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from sqlalchemy import text

from app.db.session import get_session_factory

_LOGGER = logging.getLogger("app.iam.denials")
_SAFE_VALUE = re.compile(r"[A-Za-z0-9._:*/{}-]{1,255}")
_ALLOWED_REASONS = frozenset({
    "UNENFORCED_DIMENSION",
    "STORE_SCOPE_NOT_ENFORCED",
    "ORGANIZATION_SCOPE_NOT_ENFORCED",
    "OWNER_SCOPE_NOT_ENFORCED",
    "SKU_SCOPE_NOT_ENFORCED",
    "PRODUCT_SCOPE_NOT_ENFORCED",
})
_RECORD_DAYS = 30


def record_access_denial(
    *,
    request_id: str,
    principal_id: str,
    method: str,
    route_template: str,
    error_code: str,
    stage: str,
    permission_keys: tuple[str, ...],
    scope_reason: str | None,
) -> None:
    """Best-effort audit, with strict field allowlists and no user-provided URLs."""
    if not _SAFE_VALUE.fullmatch(request_id):
        return
    if not _SAFE_VALUE.fullmatch(principal_id):
        principal_id = "anonymous"
    if not _SAFE_VALUE.fullmatch(route_template):
        route_template = "unmatched"
    if not _SAFE_VALUE.fullmatch(method) or not _SAFE_VALUE.fullmatch(error_code):
        return
    if stage not in {"permission", "data_scope", "unspecified_forbidden"}:
        return
    safe_permissions = [
        key for key in sorted(set(permission_keys))
        if isinstance(key, str) and _SAFE_VALUE.fullmatch(key)
    ][:20]
    # A scope reason comes from an internal classification, never a user value.
    reason = scope_reason if scope_reason in _ALLOWED_REASONS else None
    try:
        with get_session_factory()() as session:
            session.execute(text("""
                INSERT INTO iam_access_denial_events (
                    id, request_id, principal_id, method, route_template,
                    denial_stage, error_code, required_permissions, scope_reason
                ) VALUES (
                    :id, :request_id, :principal_id, :method, :route_template,
                    :stage, :error_code, cast(:permissions as jsonb), :scope_reason
                )
            """), {
                "id": uuid4(),
                "request_id": request_id,
                "principal_id": principal_id,
                "method": method,
                "route_template": route_template,
                "stage": stage,
                "error_code": error_code,
                "permissions": json.dumps(safe_permissions),
                "scope_reason": reason,
            })
            session.commit()
    except Exception:
        # The migration may not yet be deployed, or DB may be unavailable.
        # Never leak DB exception strings, and never modify the 403 response.
        _LOGGER.debug("denial_audit_unavailable")


def purge_expired_denials() -> int:
    """Retention is bounded by the scheduled IAM maintenance worker."""
    with get_session_factory()() as session:
        result = session.execute(
            text("""
                DELETE FROM iam_access_denial_events
                WHERE created_at < now() - make_interval(days => :days)
            """),
            {"days": _RECORD_DAYS},
        )
        session.commit()
        return int(result.rowcount or 0)
