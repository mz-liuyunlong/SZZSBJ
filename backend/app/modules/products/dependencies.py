from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal, require_principal

PRODUCT_SCOPE_RESOURCE = "product_management"

type ProductScopeProvider = Callable[[Principal, str], bool]


def get_product_scope_provider() -> ProductScopeProvider | None:
    """Trusted Product scope provider entrypoint; absent until separately integrated."""
    return None


def require_product_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        ProductScopeProvider | None,
        Depends(get_product_scope_provider),
    ],
) -> None:
    if provider is None or provider(principal, PRODUCT_SCOPE_RESOURCE) is not True:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
