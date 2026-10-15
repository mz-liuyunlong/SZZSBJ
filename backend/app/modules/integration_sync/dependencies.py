from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.config import SettingsError, get_settings
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository

type SourceAccountScopeProvider = Callable[[Principal], frozenset[str]]


def get_source_account_scope_provider() -> SourceAccountScopeProvider | None:
    """Return the configured account universe used by preview and RBAC scope resolution."""
    try:
        settings = get_settings()
    except SettingsError:
        return None

    refs = settings.product_management_preview_source_account_ref_set
    if not refs:
        return None

    preview_auth_configured = settings.product_management_preview_auth_configured

    def configured_scope(principal: Principal) -> frozenset[str]:
        if principal.user_id == PREVIEW_PRINCIPAL_ID:
            return refs if preview_auth_configured else frozenset()
        if principal.permissions:
            return refs
        return frozenset()

    return configured_scope


def require_source_account_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        SourceAccountScopeProvider | None,
        Depends(get_source_account_scope_provider),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> frozenset[str]:
    if provider is None:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    configured_refs = provider(principal)
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        allowed = configured_refs
    elif "*" in principal.permissions:
        allowed = configured_refs
    else:
        try:
            configured_values = RbacRepository(session).resolve_user_data_scope(
                user_id=int(principal.user_id),
                scope_type="source_account",
            )
        except (TypeError, ValueError):
            configured_values = set()
        if "*" in configured_values:
            allowed = configured_refs
        elif configured_values:
            allowed = frozenset(configured_values).intersection(configured_refs)
        else:
            allowed = configured_refs

    if not allowed or any(not value or value != value.strip() for value in allowed):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return frozenset(allowed)
