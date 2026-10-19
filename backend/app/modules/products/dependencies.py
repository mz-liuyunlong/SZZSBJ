from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.config import SettingsError, get_settings
from app.core.permissions import has_permission

PRODUCT_SCOPE_RESOURCE = "product_management"

type ProductScopeProvider = Callable[[Principal, str], bool]


def get_product_scope_provider() -> ProductScopeProvider | None:
    """Keep preview authorization isolated from persisted real-user RBAC scopes."""
    try:
        settings = get_settings()
    except SettingsError:
        return None

    refs = settings.product_management_preview_source_account_ref_set
    preview_auth_configured = settings.product_management_preview_auth_configured

    def configured_scope(principal: Principal, resource: str) -> bool:
        if resource != PRODUCT_SCOPE_RESOURCE:
            return False
        if principal.user_id == PREVIEW_PRINCIPAL_ID:
            return preview_auth_configured and bool(refs)
        return bool(principal.permissions)

    return configured_scope


def require_product_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        ProductScopeProvider | None,
        Depends(get_product_scope_provider),
    ],
) -> None:
    if provider is None or provider(principal, PRODUCT_SCOPE_RESOURCE) is not True:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def require_global_product_core_scope(
    principal: Annotated[Principal, Depends(require_principal)],
) -> None:
    """Fail closed until Product Core has a reviewed row-level ownership model."""
    if not has_permission(principal, "*"):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
