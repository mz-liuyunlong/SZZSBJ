"""User-based operation-log access, separate from store/account data permissions.

Preview principals are never operators. Product ownership resolves through
active IAM identities and rejects ambiguous display-name collisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.repository import IntegrationSyncRepository


@dataclass(frozen=True, slots=True)
class LogAccess:
    user_id: int
    accounts: frozenset[str]
    is_admin: bool
    owner_labels: tuple[str, ...]
    display_name: str

    def require_account(self, source_account_ref: str) -> None:
        if source_account_ref not in self.accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def resolve_log_access(
    session: Session,
    principal: Principal,
    *,
    restricted_accounts: frozenset[str] | None = None,
) -> LogAccess:
    """Derive identity only from the authenticated principal; fail closed."""
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403) from None
    if principal.user_id == PREVIEW_PRINCIPAL_ID or user_id <= 0:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    user = (
        session.execute(
            text("""
            select id, username, display_name, feishu_name, is_super_admin
            from app_users where id = :user_id and is_active = 1
            """),
            {"user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    is_admin = "*" in principal.permissions or int(user["is_super_admin"] or 0) == 1
    if not is_admin:
        is_admin = bool(
            session.scalar(
                text("""
                select exists (
                    select 1 from app_user_roles ur
                    join app_roles r on r.id = ur.role_id
                    where ur.user_id = :user_id and r.role_key = 'admin'
                )
                """),
                {"user_id": user_id},
            )
        )

    configured = IntegrationSyncRepository(session).list_configured_source_account_refs()
    if restricted_accounts is not None:
        configured = configured.intersection(restricted_accounts)
    if is_admin:
        accounts = frozenset(configured)
    else:
        scoped = RbacRepository(session).resolve_user_data_scope(
            user_id=user_id, scope_type="source_account"
        )
        accounts = frozenset(configured if "*" in scoped else configured.intersection(scoped))
    if not accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    labels = {
        str(user[k]).strip()
        for k in ("username", "display_name", "feishu_name")
        if user.get(k) is not None and str(user[k]).strip()
    }
    unique_labels = []
    for label in sorted(labels):
        matched = session.scalar(
            text("""
            select count(distinct id)
            from app_users
            where is_active = 1 and (
                username = :label or display_name = :label or feishu_name = :label
            )
            """),
            {"label": label},
        )
        if int(matched or 0) == 1:
            unique_labels.append(label)

    return LogAccess(
        user_id=user_id,
        accounts=accounts,
        is_admin=is_admin,
        owner_labels=tuple(unique_labels),
        display_name=str(user["display_name"] or user["username"]),
    )


db_session = Annotated[Session, Depends(get_db_session)]


def require_log_access(
    principal: Annotated[Principal, Depends(require_principal)],
    session: db_session,
) -> LogAccess:
    return resolve_log_access(session, principal)


def require_owned_identity(
    session: Session,
    access: LogAccess,
    *,
    account: str,
    store: str,
    item: str,
    msku: str,
    day: date,
    allow_own_history: bool = True,
) -> None:
    """Never authorize on store alone. Owner names must resolve uniquely."""
    access.require_account(account)
    if access.is_admin:
        return

    permitted = session.scalar(
        text("""
        select exists (
            select 1 from mart_listing_management_current l
            where l.source_account_ref = :account and l.store_id = :store
              and l.item_id = :item and coalesce(l.msku, '') = :msku
              and l.owner_ref = any(:labels)
            union all
            select 1 from mart_daily_sales_item_day d
            where d.source_account_ref = :account and d.store_id = :store
              and d.item_id = :item and coalesce(d.msku, '') = :msku
              and d.business_date_la = :day and d.owner_ref = any(:labels)
            union all
            select 1 from ops_manual_operation_logs m
            where :allow_history and m.source_account_ref = :account
              and m.store_id = :store and m.item_id = :item and m.msku = :msku
              and m.log_date = :day and m.owner_user_id = :user_id
        )
        """),
        {
            "account": account,
            "store": store,
            "item": item,
            "msku": msku,
            "day": day,
            "labels": list(access.owner_labels),
            "user_id": access.user_id,
            "allow_history": allow_own_history,
        },
    )
    if not permitted:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
