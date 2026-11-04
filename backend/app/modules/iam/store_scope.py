"""Account-qualified store data scopes for reviewed sales and Listing reads.

Scope values must be exact `source_account_ref|store_id` pairs. A bare store
identifier is never a global grant, because store IDs may be reused across
external source accounts. This module only resolves grants; business query
repositories must enforce them in SQL before pagination or aggregation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import has_permission
from app.modules.iam.rbac_repository import RbacRepository

STORE_SCOPE_SESSION_KEY = "szzsbj_scoped_account_stores"
_STORE_SEPARATOR = "|"

type AccountStore = tuple[str, str]


def parse_account_store(value: str) -> AccountStore:
    """Reject ambiguous or malformed legacy store-only grants."""
    if value.count(_STORE_SEPARATOR) != 1:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    account, store = value.split(_STORE_SEPARATOR, 1)
    if (
        not account
        or not store
        or account != account.strip()
        or store != store.strip()
        or any(char.isspace() for char in account)
        or any(char.isspace() for char in store)
    ):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return account, store


def resolve_account_store_scope(
    session: Session,
    principal: Principal,
) -> frozenset[AccountStore] | None:
    """Resolve persisted user-over-role store grants; None means no store bound.

    An explicit grant is always AND-ed with existing account and organization
    restrictions by the consuming repository. Unknown, unqualified or malformed
    legacy store grants are denied rather than interpreted across accounts.
    """
    if has_permission(principal, "*") or principal.user_id == PREVIEW_PRINCIPAL_ID:
        return None
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc
    values = frozenset(
        RbacRepository(session).resolve_user_data_scope(
            user_id=user_id,
            scope_type="store",
        )
    )
    if not values or "*" in values:
        return None
    pairs = frozenset(parse_account_store(value) for value in values)
    if not pairs:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return pairs
