"""Account-qualified owner binding workflow with explicit review and append-only audit.

The legacy owner-only mapping remains readable; this contract never converts a
reused UID into an unqualified global owner grant. Every write is keyed by both
source account and owner UID, and validated against current provider observations.
"""

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

router = APIRouter(tags=["iam-account-qualified-owners"])
admin_principal = Annotated[Principal, Depends(require_super_admin)]
db_session = Annotated[Session, Depends(get_db_session)]


class AccountOwnerBindingWrite(BaseModel):
    feishu_open_id: str = Field(min_length=1, max_length=128)


def _validate_identity(account: str, owner: str) -> tuple[str, str]:
    for value in (account, owner):
        if not value or value != value.strip() or len(value) > 128:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    return account, owner


def _known_identity(session: Session, account: str, owner: str) -> bool:
    """Only source-account-qualified business evidence, never display names."""
    return bool(session.execute(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM dwd_lingxing_sku_product_info_current
            WHERE source_account_ref = :account
              AND (owner_uid = :owner OR product_developer_uid = :owner)
            UNION ALL
            SELECT 1 FROM mart_daily_sales_item_day
            WHERE source_account_ref = :account AND owner_ref = :owner
            UNION ALL
            SELECT 1 FROM dws_purchase_board
            WHERE source_account_ref = :account AND owner_uid = :owner
            UNION ALL
            SELECT 1 FROM mart_listing_management_current
            WHERE source_account_ref = :account AND owner_ref = :owner
        )
        """), {"account": account, "owner": owner},
    ).scalar())


@router.get("/api/settings/organization/account-owner-candidates")
def list_account_owner_candidates(
    request: Request, _: admin_principal, session: db_session
):
    rows = session.execute(text("""
        WITH candidates AS (
            SELECT source_account_ref, owner_uid AS owner_ref
            FROM dwd_lingxing_sku_product_info_current
            WHERE nullif(btrim(owner_uid), '') IS NOT NULL
            UNION
            SELECT source_account_ref, product_developer_uid AS owner_ref
            FROM dwd_lingxing_sku_product_info_current
            WHERE nullif(btrim(product_developer_uid), '') IS NOT NULL
            UNION
            SELECT source_account_ref, owner_ref
            FROM mart_daily_sales_item_day
            WHERE nullif(btrim(owner_ref), '') IS NOT NULL
            UNION
            SELECT source_account_ref, owner_uid AS owner_ref
            FROM dws_purchase_board
            WHERE nullif(btrim(owner_uid), '') IS NOT NULL
            UNION
            SELECT source_account_ref, owner_ref
            FROM mart_listing_management_current
            WHERE nullif(btrim(owner_ref), '') IS NOT NULL
        )
        SELECT c.source_account_ref, c.owner_ref, b.feishu_open_id,
               e.name AS employee_name, coalesce(b.is_active, false) AS is_active
        FROM candidates c
        LEFT JOIN iam_org_owner_account_bindings b
          ON b.source_account_ref = c.source_account_ref
         AND b.owner_ref = c.owner_ref
        LEFT JOIN iam_feishu_employees e ON e.open_id = b.feishu_open_id
        WHERE nullif(btrim(c.source_account_ref), '') IS NOT NULL
        ORDER BY c.source_account_ref, c.owner_ref
        LIMIT 2000
    """)).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.get("/api/settings/organization/account-owner-bindings")
def list_account_owner_bindings(request: Request, _: admin_principal, session: db_session):
    rows = session.execute(text("""
        SELECT b.source_account_ref, b.owner_ref, b.feishu_open_id,
               e.name AS employee_name, b.is_active, b.reviewed_by, b.updated_at
        FROM iam_org_owner_account_bindings b
        LEFT JOIN iam_feishu_employees e ON e.open_id = b.feishu_open_id
        ORDER BY b.source_account_ref, b.owner_ref
        LIMIT 2000
    """)).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.get("/api/settings/organization/account-owner-bindings/{account}/{owner}/events")
def account_owner_binding_history(
    request: Request, account: str, owner: str, _: admin_principal, session: db_session
):
    account, owner = _validate_identity(account, owner)
    rows = session.execute(text("""
        SELECT id, source_account_ref, owner_ref, previous_open_id,
               new_open_id, actor_user_id, event_type, created_at
        FROM iam_org_owner_account_binding_events
        WHERE source_account_ref = :account AND owner_ref = :owner
        ORDER BY created_at DESC, id DESC LIMIT 100
    """), {"account": account, "owner": owner}).mappings()
    return success_response(request, data=[dict(row) for row in rows], meta=None)


@router.put("/api/settings/organization/account-owner-bindings/{account}/{owner}")
def bind_account_owner(
    request: Request,
    account: str,
    owner: str,
    payload: AccountOwnerBindingWrite,
    principal: admin_principal,
    session: db_session,
):
    account, owner = _validate_identity(account, owner)
    if not _known_identity(session, account, owner):
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            message="该账号下无当前可验证的负责人 UID 证据",
        )
    session.execute(text("SELECT pg_advisory_xact_lock(52712405)"))
    current_employee = session.execute(text("""
        SELECT open_id FROM iam_feishu_employees
        WHERE open_id = :open_id AND is_active IS TRUE
          AND is_frozen IS NOT TRUE AND is_resigned IS NOT TRUE
          AND last_seen_run_id = (
              SELECT id FROM iam_feishu_org_sync_runs
              ORDER BY applied_at DESC, id DESC LIMIT 1
          )
    """), {"open_id": payload.feishu_open_id}).scalar()
    if current_employee is None:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    previous = session.execute(text("""
        SELECT feishu_open_id, is_active
        FROM iam_org_owner_account_bindings
        WHERE source_account_ref = :account AND owner_ref = :owner
        FOR UPDATE
    """), {"account": account, "owner": owner}).mappings().first()
    if previous and previous["is_active"] and previous["feishu_open_id"] == current_employee:
        return success_response(request, data={
            "source_account_ref": account, "owner_ref": owner, "unchanged": True
        }, meta=None)
    params = {
        "account": account,
        "owner": owner,
        "open_id": current_employee,
        "actor": str(principal.user_id),
        "previous": previous["feishu_open_id"] if previous else None,
        "id": uuid4(),
    }
    session.execute(text("""
        INSERT INTO iam_org_owner_account_bindings
            (source_account_ref, owner_ref, feishu_open_id, is_active, reviewed_by)
        VALUES (:account, :owner, :open_id, true, :actor)
        ON CONFLICT (source_account_ref, owner_ref) DO UPDATE SET
            feishu_open_id = EXCLUDED.feishu_open_id,
            is_active = true, reviewed_by = EXCLUDED.reviewed_by, updated_at = now()
    """), params)
    session.execute(text("""
        INSERT INTO iam_org_owner_account_binding_events
            (id, source_account_ref, owner_ref, previous_open_id, new_open_id,
             actor_user_id, event_type)
        VALUES (:id, :account, :owner, :previous, :open_id, :actor, 'bind')
    """), params)
    session.commit()
    return success_response(request, data={
        "source_account_ref": account, "owner_ref": owner, "unchanged": False
    }, meta=None)


@router.delete("/api/settings/organization/account-owner-bindings/{account}/{owner}")
def revoke_account_owner(
    request: Request,
    account: str,
    owner: str,
    principal: admin_principal,
    session: db_session,
):
    account, owner = _validate_identity(account, owner)
    session.execute(text("SELECT pg_advisory_xact_lock(52712405)"))
    previous = session.execute(text("""
        SELECT feishu_open_id, is_active
        FROM iam_org_owner_account_bindings
        WHERE source_account_ref = :account AND owner_ref = :owner FOR UPDATE
    """), {"account": account, "owner": owner}).mappings().first()
    if previous is None or not previous["is_active"]:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    params = {
        "account": account, "owner": owner,
        "previous": previous["feishu_open_id"],
        "actor": str(principal.user_id), "id": uuid4(),
    }
    session.execute(text("""
        UPDATE iam_org_owner_account_bindings
        SET is_active = false, reviewed_by = :actor, updated_at = now()
        WHERE source_account_ref = :account AND owner_ref = :owner
    """), params)
    session.execute(text("""
        INSERT INTO iam_org_owner_account_binding_events
            (id, source_account_ref, owner_ref, previous_open_id, new_open_id,
             actor_user_id, event_type)
        VALUES (:id, :account, :owner, :previous, NULL, :actor, 'revoke')
    """), params)
    session.commit()
    return success_response(request, data={
        "source_account_ref": account, "owner_ref": owner, "revoked": True
    }, meta=None)
