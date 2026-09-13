from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.config import SettingsError, get_settings

PRODUCT_SCOPE_RESOURCE = "product_management"

type ProductScopeProvider = Callable[[Principal, str], bool]


def get_product_scope_provider() -> ProductScopeProvider | None:
    """Return the temporary Product Management preview scope or fail closed."""
    try:
        settings = get_settings()
    except SettingsError:
        return None
    if (
        not settings.product_management_preview_auth_configured
        or not settings.product_management_preview_source_account_ref_set
    ):
        return None

    def preview_scope(principal: Principal, resource: str) -> bool:
        return principal.user_id == PREVIEW_PRINCIPAL_ID and resource == PRODUCT_SCOPE_RESOURCE

    return preview_scope


def require_product_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        ProductScopeProvider | None,
        Depends(get_product_scope_provider),
    ],
) -> None:
    if provider is None or provider(principal, PRODUCT_SCOPE_RESOURCE) is not True:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
