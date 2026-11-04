"""Fail-closed backend organization scopes for the persisted Feishu directory."""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal
from app.core.permissions import has_permission
from app.modules.iam.rbac_repository import RbacRepository


def authorized_department_ids(
    session: Session,
    principal: Principal,
) -> frozenset[str] | None:
    """Return latest-snapshot descendants. None means an explicitly global grant."""
    if has_permission(principal, "*"):
        return None
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc

    granted = RbacRepository(session).resolve_user_data_scope(
        user_id=user_id, scope_type="org_department"
    )
    if "*" in granted:
        return None
    if not granted:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    query = text(
        """
        WITH RECURSIVE latest AS (
            SELECT id FROM iam_feishu_org_sync_runs
            ORDER BY applied_at DESC, id DESC LIMIT 1
        ), scope_tree AS (
            SELECT department_id, parent_department_id
            FROM iam_feishu_departments
            WHERE last_seen_run_id = (SELECT id FROM latest)
              AND department_id IN :grant_ids
            UNION
            SELECT child.department_id, child.parent_department_id
            FROM iam_feishu_departments child
            JOIN scope_tree parent ON child.parent_department_id = parent.department_id
            WHERE child.last_seen_run_id = (SELECT id FROM latest)
        )
        SELECT DISTINCT department_id FROM scope_tree
        """
    ).bindparams(bindparam("grant_ids", expanding=True))
    department_ids = frozenset(
        str(value) for value in session.execute(query, {"grant_ids": sorted(granted)}).scalars()
    )
    if not department_ids:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return department_ids


# Session-local marker is populated only for reviewed DATA-PAGES endpoints.
# Never store this in a global cache: permissions are evaluated per request.
ORG_OWNER_SCOPE_SESSION_KEY = "szzsbj_org_scoped_owner_refs"


def verified_single_account_owner_refs(
    session: Session, owner_refs: frozenset[str]
) -> frozenset[str]:
    """Return only owner UIDs backed by exactly one *known* source account.

    IAM's historical Feishu binding has only an owner_ref key, while business
    records are keyed by source account too. A reused or account-less UID cannot
    be safely turned into a global owner grant until an account-specific mapping
    is reviewed and migrated. Reject it rather than silently widening access.
    """
    normalized = frozenset(ref.strip() for ref in owner_refs if ref.strip())
    if not normalized:
        return frozenset()

    query = text(
        """
        SELECT owner_ref
        FROM (
            SELECT owner_uid AS owner_ref, source_account_ref
            FROM dwd_lingxing_sku_product_info_current
            WHERE owner_uid IN :refs
            UNION
            SELECT product_developer_uid AS owner_ref, source_account_ref
            FROM dwd_lingxing_sku_product_info_current
            WHERE product_developer_uid IN :refs
            UNION
            SELECT owner_ref, source_account_ref
            FROM mart_daily_sales_item_day
            WHERE owner_ref IN :refs
            UNION
            SELECT owner_uid AS owner_ref, source_account_ref
            FROM dws_purchase_board
            WHERE owner_uid IN :refs
            UNION
            SELECT owner_ref, source_account_ref
            FROM mart_listing_management_current
            WHERE owner_ref IN :refs
        ) AS matched
        GROUP BY owner_ref
        HAVING COUNT(DISTINCT source_account_ref) = 1
           AND bool_and(nullif(btrim(source_account_ref), '') IS NOT NULL)
        """
    ).bindparams(bindparam("refs", expanding=True))
    return frozenset(
        str(value)
        for value in session.execute(query, {"refs": sorted(normalized)}).scalars()
    )


def _require_unambiguous_owner_refs(
    session: Session, owner_refs: frozenset[str]
) -> frozenset[str]:
    verified = verified_single_account_owner_refs(session, owner_refs)
    if not verified:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return verified


def resolve_business_owner_refs(
    session: Session,
    principal: Principal,
) -> frozenset[str] | None:
    """Map authorized Feishu departments to *reviewed* business-owner IDs.

    None means an explicit global organization grant. Users without a department
    grant are restricted to their own reviewed Feishu/Lingxing owner binding; users
    without either grant or binding fail closed.
    """
    if has_permission(principal, "*"):
        return None

    from app.core.auth import PREVIEW_PRINCIPAL_ID

    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        return None

    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc

    grants = RbacRepository(session).resolve_user_data_scope(
        user_id=user_id, scope_type="org_department"
    )
    if "*" in grants:
        return None
    if not grants:
        own_owner_refs = frozenset(
            str(value)
            for value in session.execute(
                text(
                    """
                    SELECT DISTINCT b.owner_ref
                    FROM app_users u
                    JOIN iam_feishu_employees e ON e.open_id = u.feishu_open_id
                    JOIN iam_org_owner_bindings b ON b.feishu_open_id = e.open_id
                    WHERE u.id = :user_id
                      AND b.is_active IS TRUE
                      AND e.is_active IS TRUE
                      AND e.is_resigned IS NOT TRUE
                      AND e.is_frozen IS NOT TRUE
                      AND e.last_seen_run_id = (
                          SELECT id FROM iam_feishu_org_sync_runs
                          ORDER BY applied_at DESC, id DESC LIMIT 1
                      )
                    """
                ),
                {"user_id": user_id},
            ).scalars()
        )
        if not own_owner_refs:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        return _require_unambiguous_owner_refs(session, own_owner_refs)

    departments = authorized_department_ids(session, principal)
    if not departments:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    query = text(
        """
        SELECT DISTINCT b.owner_ref
        FROM iam_org_owner_bindings b
        JOIN iam_feishu_employees e ON e.open_id = b.feishu_open_id
        WHERE b.is_active IS TRUE
          AND e.is_active IS TRUE AND e.is_frozen IS NOT TRUE
          AND e.is_resigned IS NOT TRUE
          AND e.last_seen_run_id = (
              SELECT id FROM iam_feishu_org_sync_runs
              ORDER BY applied_at DESC, id DESC LIMIT 1
          )
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(e.department_ids) AS d(id)
              WHERE d.id IN :department_ids
          )
        """
    ).bindparams(bindparam("department_ids", expanding=True))
    owners = frozenset(
        str(value)
        for value in session.execute(query, {"department_ids": sorted(departments)}).scalars()
    )
    if not owners:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return _require_unambiguous_owner_refs(session, owners)
