"""Explicit Feishu organization snapshot sync. No background or startup writes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, success_response
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.permissions import require_permission, require_super_admin
from app.db.session import get_db_session
from app.modules.iam.feishu_directory_service import FeishuDirectoryService
from app.modules.iam.organization_snapshot import apply_snapshot, canonical_snapshot

router = APIRouter(tags=["iam-organization"])
db_session = Annotated[Session, Depends(get_db_session)]
admin_principal = Annotated[Principal, Depends(require_super_admin)]
org_view = Annotated[Principal, Depends(require_permission("page:settings:organization:view"))]


class ApplySnapshotRequest(BaseModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _read_feishu():
    service = FeishuDirectoryService.from_settings(get_settings())
    return service.list_visible_departments(), service.list_visible_users()


@router.get("/api/settings/organization/sync-preview")
def preview_organization_sync(request: Request, _: admin_principal):
    """Hash the current Feishu view before an independently confirmed write."""
    departments, users = _read_feishu()
    digest, normalized_departments, normalized_users = canonical_snapshot(departments, users)
    if not normalized_departments or not normalized_users:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            message="飞书返回空组织或员工数据，拒绝同步",
        )
    return success_response(
        request,
        data={
            "snapshot_hash": digest,
            "department_count": len(normalized_departments),
            "employee_count": len(normalized_users),
            "requires_confirmation": True,
        },
        meta=None,
    )


@router.post("/api/settings/organization/sync-apply")
def apply_organization_sync(
    request: Request,
    payload: ApplySnapshotRequest,
    principal: admin_principal,
    session: db_session,
):
    """Fail closed if Feishu changed between preview and apply."""
    departments, users = _read_feishu()
    try:
        run_id = apply_snapshot(
            session,
            expected_hash=payload.expected_hash,
            departments=departments,
            users=users,
            requested_by=str(principal.user_id),
        )
    except ValueError as exc:
        session.rollback()
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            message="飞书组织数据发生变化或不完整，请重新预览后确认",
        ) from exc
    session.commit()
    return success_response(request, data={"run_id": run_id, "applied": True}, meta=None)


@router.get("/api/settings/organization/sync-runs")
def list_organization_sync_runs(
    request: Request,
    _: admin_principal,
    session: db_session,
):
    rows = session.execute(
        text("""
        SELECT id, snapshot_hash, department_count, employee_count,
               requested_by, applied_at
        FROM iam_feishu_org_sync_runs
        ORDER BY applied_at DESC, id DESC LIMIT 30
        """)
    ).mappings()
    return success_response(
        request,
        data=[
            {
                "run_id": str(row["id"]),
                "snapshot_hash": row["snapshot_hash"],
                "department_count": row["department_count"],
                "employee_count": row["employee_count"],
                "requested_by": row["requested_by"],
                "applied_at": row["applied_at"],
            }
            for row in rows
        ],
        meta=None,
    )


@router.get("/api/settings/organization/snapshot")
def read_organization_snapshot(
    request: Request,
    _: org_view,
    session: db_session,
):
    """Return persisted organization data; never infer missing staff are resigned."""
    department_rows = (
        session.execute(
            text("""
        SELECT department_id, parent_department_id, name, leader_user_id
        FROM iam_feishu_departments ORDER BY name, department_id
        """)
        )
        .mappings()
        .all()
    )
    user_rows = (
        session.execute(
            text("""
        SELECT open_id, name, department_ids, is_active, is_resigned, is_frozen
        FROM iam_feishu_employees ORDER BY name, open_id
        """)
        )
        .mappings()
        .all()
    )
    last_run = (
        session.execute(
            text("""
        SELECT applied_at, snapshot_hash FROM iam_feishu_org_sync_runs
        ORDER BY applied_at DESC, id DESC LIMIT 1
        """)
        )
        .mappings()
        .first()
    )
    return success_response(
        request,
        data={
            "departments": [dict(row) for row in department_rows],
            "users": [dict(row) for row in user_rows],
            "last_synced_at": last_run["applied_at"] if last_run else None,
            "snapshot_hash": last_run["snapshot_hash"] if last_run else None,
            "read_only": True,
        },
        meta=None,
    )
