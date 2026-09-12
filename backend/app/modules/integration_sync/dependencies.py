from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal, require_principal

type SourceAccountScopeProvider = Callable[[Principal], frozenset[str]]


def get_source_account_scope_provider() -> SourceAccountScopeProvider | None:
    """Trusted opaque account-scope entrypoint; absent providers fail closed."""
    return None


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
