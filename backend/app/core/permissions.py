from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal, require_principal


def require_permission(permission_key: str) -> Callable[..., Principal]:
    if not permission_key or permission_key != permission_key.strip():
        raise ValueError("permission_key must be a non-empty canonical value")

    def dependency(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> Principal:
        if permission_key not in principal.permissions:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        return principal

    return dependency
