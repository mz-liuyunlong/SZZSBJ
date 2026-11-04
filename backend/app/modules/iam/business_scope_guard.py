"""Fail-closed enforcement for persisted data scopes not yet covered by business SQL.

This guard protects *existing* role/user grants, not only new scope assignments.
It only runs on business endpoints and never mutates permissions. Unknown legacy
grants must not silently widen the account scope or be bypassed with a URL filter.
"""

from __future__ import annotations

import re
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
    "/api/sales/order-profit",
    "/api/sales/order-profit/export",
    "/api/sales/order-profit/trend",
    "/api/sales/order-profit/filter-options",
    "/api/listings/walmart",
    "/api/listings/walmart/summary",
    "/api/listings/walmart/filter-options",
    "/api/listings/walmart/export",
    "/api/pmc/purchase/board",
    "/api/pmc/purchase/board/summary",
    "/api/pmc/purchase/plans/pending",
})
_STORE_REVIEWED_GET_PREFIXES = ("/api/pmc/purchase/orders/",)
_STORE_REVIEWED_ADDITIONAL_GET = frozenset({
    "/api/after-sales/refunds/overview",
    "/api/after-sales/refunds/product-analysis",
    "/api/after-sales/refunds/items",
    "/api/warehouse/wfs-fee-cases",
    "/api/warehouse/wfs-fee-alerts",
    "/api/approvals",
    "/api/approvals/summary",
})
_STORE_REVIEWED_GET_PATTERNS = (
    re.compile(r"/api/warehouse/wfs-fee-cases/[0-9A-Fa-f-]{36}"),
    re.compile(r"/api/approvals/[0-9A-Fa-f-]{36}"),
    re.compile(r"/api/approvals/wfs-cases/[0-9A-Fa-f-]{36}/detail"),
    re.compile(r"/api/approvals/legacy/[0-9A-Fa-f-]{36}"),
)
_STORE_REVIEWED_POST_PATTERNS = (
    re.compile(r"/api/warehouse/wfs-fee-cases/[0-9A-Fa-f-]{36}/(follow|archive-request|archive-review|mark-recovered)"),
    re.compile(r"/api/approvals/wfs-cases/[0-9A-Fa-f-]{36}(/decision)?"),
    re.compile(r"/api/approvals/[0-9A-Fa-f-]{36}/(decision|supplement)"),
)
_STORE_REVIEWED_PUT_PATTERNS = (
    re.compile(r"/api/warehouse/wfs-fee-alerts/[0-9A-Fa-f-]{36}/case"),
)


def _store_route_reviewed(method: str, path: str) -> bool:
    if method == "GET":
        return (
            path in _STORE_REVIEWED_GET_PATHS
            or path in _STORE_REVIEWED_ADDITIONAL_GET
            or any(path.startswith(prefix) for prefix in _STORE_REVIEWED_GET_PREFIXES)
            or any(pattern.fullmatch(path) for pattern in _STORE_REVIEWED_GET_PATTERNS)
        )
    if method == "POST":
        return any(pattern.fullmatch(path) for pattern in _STORE_REVIEWED_POST_PATTERNS)
    if method == "PUT":
        return any(pattern.fullmatch(path) for pattern in _STORE_REVIEWED_PUT_PATTERNS)
    return False
_ORG_REVIEWED_GET_PATHS = _STORE_REVIEWED_GET_PATHS | frozenset({
    "/api/after-sales/refunds/overview",
    "/api/after-sales/refunds/product-analysis",
    "/api/after-sales/refunds/items",
    "/api/product-management/skus",
    "/api/product-management/skus/summary",
    "/api/product-management/options",
    "/api/product-management/skus/export",
    "/api/warehouse/wfs-fee-cases",
    "/api/warehouse/wfs-fee-alerts",
    "/api/approvals",
    "/api/approvals/summary",
})
_ORG_REVIEWED_GET_PREFIXES = _STORE_REVIEWED_GET_PREFIXES
_ORG_REVIEWED_GET_PATTERNS = (
    re.compile(r"/api/product-management/skus/[0-9A-Fa-f-]{36}(/pricing-breakdown)?"),
    re.compile(r"/api/warehouse/wfs-fee-cases/[0-9A-Fa-f-]{36}"),
    re.compile(r"/api/approvals/[0-9A-Fa-f-]{36}"),
    re.compile(r"/api/approvals/wfs-cases/[0-9A-Fa-f-]{36}/detail"),
    re.compile(r"/api/approvals/legacy/[0-9A-Fa-f-]{36}"),
)
_ORG_REVIEWED_WRITE_PATHS = frozenset({
    "/api/product-management/skus/export",
})
_ORG_REVIEWED_WRITE_PATTERNS = (
    re.compile(r"/api/warehouse/wfs-fee-cases/[0-9A-Fa-f-]{36}/(follow|archive-request|archive-review|mark-recovered)"),
    re.compile(r"/api/approvals/wfs-cases/[0-9A-Fa-f-]{36}(/decision)?"),
    re.compile(r"/api/approvals/[0-9A-Fa-f-]{36}/(decision|supplement)"),
)
_ORG_REVIEWED_PUT_PATTERNS = (
    re.compile(r"/api/warehouse/wfs-fee-alerts/[0-9A-Fa-f-]{36}/case"),
)
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
          AND scope_type IN ('store', 'owner', 'sku', 'product', 'org_department')
        UNION ALL
        SELECT 'role' AS origin, r.scope_type, r.scope_value
        FROM app_user_roles ur
        JOIN app_role_data_scopes r ON r.role_id = ur.role_id
        WHERE ur.user_id = :user_id
          AND r.scope_type IN ('store', 'owner', 'sku', 'product', 'org_department')
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
        for kind in _UNENFORCED_DIMENSIONS | {"store", "org_department"}
    }


def _has_own_feishu_owner_binding(session: Session, user_id: int) -> bool:
    """Own reviewed identity also restricts business routes without a department grant."""
    return bool(session.scalar(text("""
        SELECT EXISTS (
            SELECT 1
            FROM app_users u
            JOIN iam_feishu_employees e ON e.open_id = u.feishu_open_id
            WHERE u.id = :user_id
              AND e.is_active IS TRUE
              AND e.is_resigned IS NOT TRUE
              AND e.is_frozen IS NOT TRUE
              AND e.last_seen_run_id = (
                  SELECT id FROM iam_feishu_org_sync_runs
                  ORDER BY applied_at DESC, id DESC LIMIT 1
              )
              AND (
                  EXISTS (
                      SELECT 1 FROM iam_org_owner_account_bindings b
                      WHERE b.feishu_open_id = e.open_id AND b.is_active IS TRUE
                  )
                  OR EXISTS (
                      SELECT 1 FROM iam_org_owner_bindings b
                      WHERE b.feishu_open_id = e.open_id AND b.is_active IS TRUE
                  )
              )
        )
    """), {"user_id": user_id}))


def _org_route_reviewed(method: str, path: str) -> bool:
    if method == "GET":
        return (
            path in _ORG_REVIEWED_GET_PATHS
            or any(path.startswith(prefix) for prefix in _ORG_REVIEWED_GET_PREFIXES)
            or any(pattern.fullmatch(path) for pattern in _ORG_REVIEWED_GET_PATTERNS)
        )
    if method == "POST":
        return (
            path in _ORG_REVIEWED_WRITE_PATHS
            or any(pattern.fullmatch(path) for pattern in _ORG_REVIEWED_WRITE_PATTERNS)
        )
    if method == "PUT":
        return any(pattern.fullmatch(path) for pattern in _ORG_REVIEWED_PUT_PATTERNS)
    return False


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

    departments = scoped["org_department"]
    organization_restricted = (
        bool(departments and "*" not in departments)
        or (
            not departments
            and _has_own_feishu_owner_binding(session, user_id)
        )
    )
    if organization_restricted and not _org_route_reviewed(request.method, path):
        raise ApiError(
            code=ErrorCode.DATA_SCOPE_DENIED,
            status_code=403,
            details={"scope_reason": "ORGANIZATION_SCOPE_NOT_ENFORCED"},
        )

    stores = scoped["store"]
    if stores and "*" not in stores:
        reviewed = _store_route_reviewed(request.method, path)
        if not reviewed:
            raise ApiError(
                code=ErrorCode.DATA_SCOPE_DENIED,
                status_code=403,
                details={"scope_reason": "STORE_SCOPE_NOT_ENFORCED"},
            )
