"""Fail-closed enforcement for persisted data scopes not yet covered by business SQL.

This guard protects *existing* role/user grants, not only new scope assignments.
It only runs on business endpoints and never mutates permissions. Unknown legacy
grants must not silently widen the account scope or be bypassed with a URL filter.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, get_optional_principal
from app.db.session import get_db_session

_UNENFORCED_DIMENSIONS = frozenset({"owner", "sku", "product"})
_STORE_REVIEWED_GET_PATHS = frozenset({
    "/api/data-pages/filter-options",
    "/api/sales/daily-sales",
    "/api/sales/daily-sales/export",
    "/api/listings/walmart",
    "/api/listings/walmart/summary",
    "/api/listings/walmart/filter-options",
    "/api/listings/walmart/export",
    "/api/pmc/purchase/board",
    "/api/pmc/purchase/board/summary",
    "/api/pmc/purchase/plans/pending",
})
_STORE_REVIEWED_GET_PREFIXES = ("/api/pmc/purchase/orders/",)
_NON_BUSINESS_PREFIXES = (
    "/api/settings/",
    "/api/auth/",
    "/api/integrations/",
    "/api/health",
)


def _scope_sources(session: Session, user_id: int) -> dict[str, frozenset[str]]:
    """User-level values override role values within the same dimension."""
    rows = session.execute(
        text("""
        SELECT 'user' AS origin, scope_type, scope_value
        FROM app_user_data_scopes
        WHERE user_id = :user_id
          AND scope_type IN ('store', 'owner', 'sku', 'product')
        UNION ALL
        SELECT 'role' AS origin, r.scope_type, r.scope_value
        FROM app_user_roles ur
        JOIN app_role_data_scopes r ON r.role_id = ur.role_id
        WHERE ur.user_id = :user_id
          AND r.scope_type IN ('store', 'owner', 'sku', 'product')
        """),
        {"user_id": user_id},
    ).mappings()
    user: dict[str, set[str]] = {}
    role: dict[str, set[str]] = {}
    for row in rows:
        kind = str(row["scope_type"])
        if row["origin"] == "user":
            user.setdefault(kind, set()).add(str(row["scope_value"]))
        else:
            role.setdefault(kind, set()).add(str(row["scope_value"]))
    return {
        kind: frozenset(user[kind] if kind in user else role.get(kind, set()))
        for kind in _UNENFORCED_DIMENSIONS | {"store"}
    }


def require_business_scope_coverage(
    request: Request,
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    session: Annotated[Session, Depends(get_db_session)],
) -> None:
    """Deny unsupported dimensional grants on unreviewed business endpoints.

    Super-administrators and the dedicated preview principal retain their
    existing explicit access model. Settings/auth/callback paths are unaffected
    to allow administrators to correct bad grants.
    """
    if principal is None or "*" in principal.permissions or principal.user_id == PREVIEW_PRINCIPAL_ID:
        return
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(_NON_BUSINESS_PREFIXES):
        return
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc

    scoped = _scope_sources(session, user_id)
    if any(scoped[kind] for kind in _UNENFORCED_DIMENSIONS):
        raise ApiError(
            code=ErrorCode.DATA_SCOPE_DENIED,
            status_code=403,
            details={"scope_reason": "UNENFORCED_DIMENSION"},
        )

    stores = scoped["store"]
    if stores and "*" not in stores:
        reviewed = (
            request.method == "GET"
            and (
                path in _STORE_REVIEWED_GET_PATHS
                or any(path.startswith(prefix) for prefix in _STORE_REVIEWED_GET_PREFIXES)
            )
        )
        if not reviewed:
            raise ApiError(
                code=ErrorCode.DATA_SCOPE_DENIED,
                status_code=403,
                details={"scope_reason": "STORE_SCOPE_NOT_ENFORCED"},
            )
