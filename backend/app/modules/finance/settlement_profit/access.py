"""Permissions and data scope for the settlement profit API (PRP §5).

- Store scope comes from RBAC ``store`` grants (``*`` = all stores); no grant → 403.
- Owner scope (运营负责人) applies only to users without any finance action permission
  who have ``owner`` grants; finance roles and management are not owner-limited.
- ``__unmapped__`` (待指定 of movements whose store_code maps to no store) is never a
  store: it is only visible to finance users whose store scope is all stores.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository

from .keys import UNMAPPED_STORE_ID

VIEW = "page:finance:settlement-profit:view"
ADJUST = "action:finance:settlement-profit:adjust"
REVIEW_FIRST = "action:finance:settlement-profit:review-first"
REVIEW_FINAL = "action:finance:settlement-profit:review-final"
CLOSE_MONTH = "action:finance:settlement-profit:close-month"
CONFIG = "action:finance:settlement-profit:config"
FIELD_COST = "field:finance:settlement-profit:cost"
FIELD_NET_PROFIT = "field:finance:settlement-profit:net-profit"
FIELD_COMPANY_COST = "field:finance:settlement-profit:company-cost"
FINANCE_ACTIONS = (ADJUST, REVIEW_FIRST, REVIEW_FINAL, CLOSE_MONTH, CONFIG)

UNMAPPED_STORE_LABEL = "未对上店铺"


@dataclass(frozen=True)
class ScopeGrants:
    stores: frozenset[str]
    owners: frozenset[str]


def load_scope_grants(
    principal: Annotated[Principal, Depends(require_permission(VIEW))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ScopeGrants:
    if has_permission(principal, "*"):
        return ScopeGrants(frozenset({"*"}), frozenset())
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
    repo = RbacRepository(session)
    return ScopeGrants(
        frozenset(repo.resolve_user_data_scope(user_id=user_id, scope_type="store")),
        frozenset(repo.resolve_user_data_scope(user_id=user_id, scope_type="owner")),
    )


@dataclass(frozen=True)
class SettlementAccess:
    principal: Principal
    all_stores: bool
    store_ids: frozenset[str]
    owner_ids: frozenset[str] | None  # None: not owner-limited

    def can(self, permission_key: str) -> bool:
        return has_permission(self.principal, permission_key)

    @property
    def actor_id(self) -> str:
        return self.principal.user_id

    @property
    def is_finance(self) -> bool:
        return any(self.can(k) for k in FINANCE_ACTIONS)

    @property
    def actor_role(self) -> str:
        if has_permission(self.principal, "*"):
            return "super_admin"
        if self.can(CLOSE_MONTH) or self.can(CONFIG) or self.can(REVIEW_FINAL):
            return "finance_lead"
        if self.is_finance:
            return "finance"
        return "owner" if self.owner_ids is not None else "viewer"

    @property
    def sees_unmapped(self) -> bool:
        """Only all-store finance users see ``__unmapped__`` 待指定 rows."""
        return self.all_stores and self.is_finance and self.owner_ids is None

    @property
    def can_see_cost(self) -> bool:
        return self.can(FIELD_COST)

    @property
    def can_see_net_profit(self) -> bool:
        return self.can(FIELD_NET_PROFIT)

    def require(self, permission_key: str) -> None:
        if not self.can(permission_key):
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                details={"required_permission": permission_key},
            )

    def require_not_owner_limited(self) -> None:
        if self.owner_ids is not None:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    def store_visible(self, store_id: str) -> bool:
        if store_id == UNMAPPED_STORE_ID:
            return self.sees_unmapped
        return self.all_stores or store_id in self.store_ids

    def owner_visible(self, owner_ref: str | None) -> bool:
        return self.owner_ids is None or (owner_ref is not None and owner_ref in self.owner_ids)

    def requested_stores(self, store_ids: Iterable[str] | None) -> list[str] | None:
        """Validate a store filter; None = every store in scope (``__unmapped__`` excluded)."""
        wanted = [s for s in (store_ids or []) if s]
        if UNMAPPED_STORE_ID in wanted:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                details={"store_ids": f"{UNMAPPED_STORE_ID} is not a store"},
            )
        if not wanted:
            return None if self.all_stores else sorted(self.store_ids)
        if not self.all_stores and any(s not in self.store_ids for s in wanted):
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        return sorted(set(wanted))


def get_settlement_access(
    principal: Annotated[Principal, Depends(require_permission(VIEW))],
    grants: Annotated[ScopeGrants, Depends(load_scope_grants)],
) -> SettlementAccess:
    stores = {s for s in grants.stores if s and s != UNMAPPED_STORE_ID}
    all_stores = "*" in stores
    if not all_stores and not stores:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    is_finance = has_permission(principal, "*") or any(
        has_permission(principal, k) for k in FINANCE_ACTIONS
    )
    owners = {o for o in grants.owners if o}
    owner_limited = not is_finance and bool(owners) and "*" not in owners
    return SettlementAccess(
        principal=principal,
        all_stores=all_stores,
        store_ids=frozenset() if all_stores else frozenset(stores),
        owner_ids=frozenset(owners) if owner_limited else None,
    )
