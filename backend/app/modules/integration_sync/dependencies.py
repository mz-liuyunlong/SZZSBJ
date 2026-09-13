from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.config import SettingsError, get_settings

type SourceAccountScopeProvider = Callable[[Principal], frozenset[str]]


def get_source_account_scope_provider() -> SourceAccountScopeProvider | None:
    """Return configured preview account scope without exposing its values."""
    try:
        settings = get_settings()
    except SettingsError:
        return None
    refs = settings.product_management_preview_source_account_ref_set
    if not settings.product_management_preview_auth_configured or not refs:
        return None

    def preview_scope(principal: Principal) -> frozenset[str]:
        return refs if principal.user_id == PREVIEW_PRINCIPAL_ID else frozenset()

    return preview_scope


def require_source_account_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        SourceAccountScopeProvider | None,
        Depends(get_source_account_scope_provider),
    ],
) -> frozenset[str]:
    if provider is None:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    allowed = provider(principal)
    if not allowed or any(not value or value != value.strip() for value in allowed):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return allowed
