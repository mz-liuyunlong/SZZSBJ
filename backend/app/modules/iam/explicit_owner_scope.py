"""Account-qualified explicit owner grants for reviewed read-only data pages.

Unlike an approved Feishu owner binding, this dimension represents a persisted
user/role data scope. A bare owner UID is never an account-wide grant because
UIDs may be reused in multiple Lingxing source accounts.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import has_permission
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.iam.store_scope import parse_account_store

OWNER_SCOPE_SESSION_KEY = "szzsbj_scoped_account_owner_grants"


def resolve_explicit_owner_scope(
    session: Session,
    principal: Principal,
) -> frozenset[tuple[str, str]] | None:
    """User-over-role values; None means no explicit owner dimension.

    An unqualified owner ID or wildcard is rejected, rather than being
    interpreted as permission across every account. New grants remain blocked
    by the global configuration policy until all business modules enforce it.
    """
    if has_permission(principal, "*") or principal.user_id == PREVIEW_PRINCIPAL_ID:
        return None
    try:
        user_id = int(principal.user_id)
    except (ValueError, TypeError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc
    values = frozenset(RbacRepository(session).resolve_user_data_scope(
        user_id=user_id, scope_type="owner"
    ))
    if not values:
        return None
    if "*" in values:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    pairs = frozenset(parse_account_store(value) for value in values)
    if not pairs:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return pairs
