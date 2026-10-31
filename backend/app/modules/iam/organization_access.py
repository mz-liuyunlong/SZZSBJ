"""Fail-closed backend organization scopes for the persisted Feishu directory."""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal
from app.modules.iam.rbac_repository import RbacRepository


def authorized_department_ids(
    session: Session,
    principal: Principal,
) -> frozenset[str] | None:
    """Return latest-snapshot descendants. None means an explicitly global grant."""
    if "*" in principal.permissions:
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
        str(value)
        for value in session.execute(query, {"grant_ids": sorted(granted)}).scalars()
    )
    if not department_ids:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return department_ids
