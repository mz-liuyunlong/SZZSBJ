from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.config import SettingsError, get_settings
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.repository import IntegrationSyncRepository

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
        if principal.user_id != PREVIEW_PRINCIPAL_ID:
            return frozenset()
        return refs if preview_auth_configured else frozenset()

    return configured_scope


def require_source_account_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        SourceAccountScopeProvider | None,
        Depends(get_source_account_scope_provider),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> frozenset[str]:
    configured_refs = provider(principal) if provider is not None else frozenset()
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        allowed = configured_refs
    else:
        # Real principals use the persisted governance registry as the account universe.
        # Explicit dependency overrides may still supply a synthetic universe in tests.
        configured_refs = (
            configured_refs
            or IntegrationSyncRepository(session).list_configured_source_account_refs()
        )
        try:
            user_id = int(principal.user_id)
        except (TypeError, ValueError):
            # Only the dedicated preview principal may use configured in-memory
            # scope. Every other principal must resolve to a persisted IAM user;
            # otherwise a forged non-numeric id could inherit the full registry.
            allowed = frozenset()
        else:
            if "*" in principal.permissions:
                allowed = configured_refs
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
