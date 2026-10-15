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
    if principal.user_id == PREVIEW_PRINCIPAL_ID or "*" in principal.permissions:
        allowed = configured_refs
    else:
        try:
            user_id = int(principal.user_id)
        except (TypeError, ValueError):
            # Synthetic principals used by isolated API tests and temporary
            # compatibility callers do not have persisted IAM scope rows.
            allowed = configured_refs if principal.permissions else frozenset()
        else:
            scoped_values = RbacRepository(session).resolve_user_data_scope(
                user_id=user_id,
                scope_type="source_account",
            )
            if "*" in scoped_values:
                allowed = configured_refs
            elif scoped_values:
                allowed = frozenset(scoped_values).intersection(configured_refs)
            else:
                allowed = frozenset()

    if not allowed or any(not value or value != value.strip() for value in allowed):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return frozenset(allowed)
