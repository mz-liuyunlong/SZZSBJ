"""Stable IAM ownership checks for operation logs.

The only business-owner link is an explicit account-scoped Lingxing UID mapping
to app_users.id. Human names and mutable usernames are display-only.
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
    display_name: str

    def require_account(self, source_account_ref: str) -> None:
        if source_account_ref not in self.accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def owns_sku_sql(alias: str) -> str:
    """SQL predicate using *verified* external UID, never owner_ref or names.

    Reject an SKU with conflicting/missing Lingxing UID rows. All aliases are
    developer constants so no request parameters become SQL identifiers.
    """
    if alias not in {"l", "d", "s"}:
        raise ValueError("Invalid trusted table alias")
    return f"""exists (
        select 1
        from dwd_lingxing_sku_product_info_current pi
        join ops_lingxing_owner_user_mappings map
          on map.source_account_ref = pi.source_account_ref
         and map.owner_uid = btrim(pi.owner_uid)
        where pi.source_account_ref = {alias}.source_account_ref
          and pi.lingxing_sku_code = {alias}.local_sku
          and nullif(btrim(pi.owner_uid), '') is not null
          and map.app_user_id = :user_id
          and not exists (
            select 1 from dwd_lingxing_sku_product_info_current conflict
            where conflict.source_account_ref = pi.source_account_ref
              and conflict.lingxing_sku_code = pi.lingxing_sku_code
              and nullif(btrim(conflict.owner_uid), '')
                  is distinct from nullif(btrim(pi.owner_uid), '')
          )
    )"""


def product_owner_sql() -> str:
    """Use current Listing or dated sales identity to confirm assigned user."""
    return f"""exists (
        select 1 from mart_listing_management_current l
        where l.source_account_ref = :account and l.store_id = :store
          and l.item_id = :item and coalesce(l.msku, '') = :msku
          and {owns_sku_sql("l")}
        union all
        select 1 from mart_daily_sales_item_day d
        where d.source_account_ref = :account and d.store_id = :store
          and d.item_id = :item and coalesce(d.msku, '') = :msku
          and d.business_date_la = :day and {owns_sku_sql("d")}
    )"""


def resolve_log_access(
    session: Session,
    principal: Principal,
    *,
    restricted_accounts: frozenset[str] | None = None,
) -> LogAccess:
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403) from None
    if principal.user_id == PREVIEW_PRINCIPAL_ID or user_id <= 0:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    user = (
        session.execute(
            text("""
            select id, username, display_name, is_super_admin
            from app_users where id = :user_id and is_active = 1
        """),
            {"user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    is_admin = int(user["is_super_admin"] or 0) == 1
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
    return LogAccess(
        user_id=user_id,
        accounts=accounts,
        is_admin=is_admin,
        display_name=str(user["display_name"] or user["username"]),
    )


db_session = Annotated[Session, Depends(get_db_session)]


def require_log_access(
    principal: Annotated[Principal, Depends(require_principal)],
    session: db_session,
) -> LogAccess:
    return resolve_log_access(session, principal)


def is_current_assignee(
    session: Session,
    access: LogAccess,
    *,
    account: str,
    store: str,
    item: str,
    msku: str,
    day: date,
) -> bool:
    access.require_account(account)
    if access.is_admin:
        return True
    return bool(
        session.scalar(
            text("select " + product_owner_sql()),
            {
                "user_id": access.user_id,
                "account": account,
                "store": store,
                "item": item,
                "msku": msku,
                "day": day,
            },
        )
    )


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
    """Can work on currently assigned products, or own archived notes only."""
    if is_current_assignee(
        session, access, account=account, store=store, item=item, msku=msku, day=day
    ):
        return
    if allow_own_history:
        own = session.scalar(
            text("""
                select exists (
                    select 1 from ops_manual_operation_logs
                    where source_kind = 'manual' and created_by_user_id = :user_id
                      and source_account_ref = :account and log_date = :day
                      and store_id = :store and item_id = :item and msku = :msku
                )
            """),
            {
                "user_id": access.user_id,
                "account": account,
                "day": day,
                "store": store,
                "item": item,
                "msku": msku,
            },
        )
        if own:
            return
    raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
