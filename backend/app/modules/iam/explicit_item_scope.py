"""Strict account-qualified SKU and Item ID scopes for vetted read-only MARTs.

SKU means source-account + local SKU; product means source-account + platform
Item ID. These are not interchangeable with MSKU, ASIN, free-text product name,
or unqualified historical keys. Unknown legacy grants never act globally.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.core.permissions import has_permission
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.iam.store_scope import parse_account_store

SKU_SCOPE_SESSION_KEY = "szzsbj_scoped_account_local_skus"
PRODUCT_SCOPE_SESSION_KEY = "szzsbj_scoped_account_item_ids"


def resolve_explicit_identity_scope(
    session: Session, principal: Principal, *, scope_type: str
) -> frozenset[tuple[str, str]] | None:
    if scope_type not in {"sku", "product"}:
        raise ValueError("Unsupported identity scope type")
    if has_permission(principal, "*") or principal.user_id == PREVIEW_PRINCIPAL_ID:
        return None
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from exc
    raw = frozenset(RbacRepository(session).resolve_user_data_scope(
        user_id=user_id, scope_type=scope_type
    ))
    if not raw:
        return None
    if "*" in raw:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    result = frozenset(parse_account_store(value) for value in raw)
    if not result:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return result
