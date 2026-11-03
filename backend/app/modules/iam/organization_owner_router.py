"""Explicit audited Feishu/Lingxing UID binding, super-administrator only."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, success_response
from app.core.auth import Principal
from app.core.permissions import require_super_admin
from app.db.session import get_db_session

router = APIRouter(tags=["iam-organization-owners"])
admin_principal = Annotated[Principal, Depends(require_super_admin)]
db_session = Annotated[Session, Depends(get_db_session)]


class OwnerBindingWrite(BaseModel):
    feishu_open_id: str = Field(min_length=1, max_length=128)


def _business_owner_exists(session: Session, owner_ref: str) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM dwd_lingxing_sku_product_info_current
                    WHERE owner_uid = :owner_ref OR product_developer_uid = :owner_ref
                    UNION ALL
                    SELECT 1 FROM mart_daily_sales_item_day WHERE owner_ref = :owner_ref
                    UNION ALL
                    SELECT 1 FROM dws_purchase_board WHERE owner_uid = :owner_ref
                    UNION ALL
                    SELECT 1 FROM mart_listing_management_current WHERE owner_ref = :owner_ref
                )
                """
            ),
            {"owner_ref": owner_ref},
        ).scalar()
    )


@router.get("/api/settings/organization/owner-candidates")
def list_owner_candidates(request: Request, _: admin_principal, session: db_session):
    rows = session.execute(
        text("""
        SELECT candidates.owner_ref, b.feishu_open_id, e.name AS employee_name,
               coalesce(b.is_active, false) AS is_active
        FROM (
            SELECT owner_ref FROM (
                SELECT owner_uid AS owner_ref
                FROM dwd_lingxing_sku_product_info_current
                WHERE owner_uid IS NOT NULL AND trim(owner_uid) <> ''
                UNION
                SELECT product_developer_uid AS owner_ref
                FROM dwd_lingxing_sku_product_info_current
                WHERE product_developer_uid IS NOT NULL AND trim(product_developer_uid) <> ''
                UNION
                SELECT owner_ref FROM mart_daily_sales_item_day
                WHERE owner_ref IS NOT NULL AND trim(owner_ref) <> ''
                UNION
                SELECT owner_uid AS owner_ref FROM dws_purchase_board
                WHERE owner_uid IS NOT NULL AND trim(owner_uid) <> ''
                UNION
                SELECT owner_ref FROM mart_listing_management_current
                WHERE owner_ref IS NOT NULL AND trim(owner_ref) <> ''
            ) business_owners
        ) candidates
        LEFT JOIN iam_org_owner_bindings b ON b.owner_ref = candidates.owner_ref
        LEFT JOIN iam_feishu_employees e ON e.open_id = b.feishu_open_id
        ORDER BY candidates.owner_ref
        """)
    ).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.get("/api/settings/organization/owner-bindings")
def list_owner_bindings(request: Request, _: admin_principal, session: db_session):
    rows = session.execute(
        text("""
        SELECT b.owner_ref, b.feishu_open_id, e.name AS employee_name,
               b.is_active, b.reviewed_by, b.updated_at
        FROM iam_org_owner_bindings b
        LEFT JOIN iam_feishu_employees e ON e.open_id = b.feishu_open_id
        ORDER BY b.owner_ref
        """)
    ).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.put("/api/settings/organization/owner-bindings/{owner_ref}")
def set_owner_binding(
    request: Request,
    owner_ref: str,
    payload: OwnerBindingWrite,
    principal: admin_principal,
    session: db_session,
):
    owner_ref = owner_ref.strip()
    if not owner_ref or len(owner_ref) > 128:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    # A binding is accepted only when the Lingxing UID exists in real business data.
    if not _business_owner_exists(session, owner_ref):
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            message="负责人 UID 不存在于当前业务数据，不能建立绑定",
        )
    # A mapping never trusts name-matching; both identities are explicitly reviewed.
    current = session.execute(
        text("""
        SELECT open_id FROM iam_feishu_employees
        WHERE open_id = :open_id AND is_active IS TRUE
          AND is_resigned IS NOT TRUE AND is_frozen IS NOT TRUE
          AND last_seen_run_id = (
              SELECT id FROM iam_feishu_org_sync_runs
              ORDER BY applied_at DESC, id DESC LIMIT 1
          )
        """),
        {"open_id": payload.feishu_open_id},
    ).scalar()
    if not current:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            message="未找到最新有效飞书员工，无法建立负责人绑定",
        )
    session.execute(text("SELECT pg_advisory_xact_lock(52712404)"))
    previous = (
        session.execute(
            text("""
        SELECT feishu_open_id, is_active FROM iam_org_owner_bindings
        WHERE owner_ref = :owner_ref FOR UPDATE
        """),
            {"owner_ref": owner_ref},
        )
        .mappings()
        .first()
    )
    if previous and previous["is_active"] and previous["feishu_open_id"] == current:
        return success_response(
            request, data={"owner_ref": owner_ref, "unchanged": True}, meta=None
        )
    session.execute(
        text("""
        INSERT INTO iam_org_owner_bindings (owner_ref, feishu_open_id, is_active, reviewed_by)
        VALUES (:owner_ref, :open_id, true, :actor)
        ON CONFLICT (owner_ref) DO UPDATE SET
          feishu_open_id = EXCLUDED.feishu_open_id, is_active = true,
          reviewed_by = EXCLUDED.reviewed_by, updated_at = now()
        """),
        {"owner_ref": owner_ref, "open_id": current, "actor": str(principal.user_id)},
    )
    session.execute(
        text("""
        INSERT INTO iam_org_owner_binding_events
            (id, owner_ref, previous_open_id, new_open_id, actor_user_id, event_type)
        VALUES (:id, :owner_ref, :previous, :new, :actor, 'bind')
        """),
        {
            "id": uuid4(),
            "owner_ref": owner_ref,
            "previous": previous["feishu_open_id"] if previous else None,
            "new": current,
            "actor": str(principal.user_id),
        },
    )
    session.commit()
    return success_response(request, data={"owner_ref": owner_ref, "unchanged": False}, meta=None)


@router.delete("/api/settings/organization/owner-bindings/{owner_ref}")
def revoke_owner_binding(
    request: Request,
    owner_ref: str,
    principal: admin_principal,
    session: db_session,
):
    session.execute(text("SELECT pg_advisory_xact_lock(52712404)"))
    previous = (
        session.execute(
            text("""
        SELECT feishu_open_id, is_active FROM iam_org_owner_bindings
        WHERE owner_ref = :owner_ref FOR UPDATE
        """),
            {"owner_ref": owner_ref},
        )
        .mappings()
        .first()
    )
    if not previous or not previous["is_active"]:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    session.execute(
        text("""
        UPDATE iam_org_owner_bindings
        SET is_active = false, reviewed_by = :actor, updated_at = now()
        WHERE owner_ref = :owner_ref
        """),
        {"owner_ref": owner_ref, "actor": str(principal.user_id)},
    )
    session.execute(
        text("""
        INSERT INTO iam_org_owner_binding_events
            (id, owner_ref, previous_open_id, new_open_id, actor_user_id, event_type)
        VALUES (:id, :owner_ref, :previous, null, :actor, 'revoke')
        """),
        {
            "id": uuid4(),
            "owner_ref": owner_ref,
            "previous": previous["feishu_open_id"],
            "actor": str(principal.user_id),
        },
    )
    session.commit()
    return success_response(request, data={"owner_ref": owner_ref, "revoked": True}, meta=None)
