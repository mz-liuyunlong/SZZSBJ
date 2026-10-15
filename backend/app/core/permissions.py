from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal, require_principal
from app.core.permission_policy_v2 import permission_for_request


def has_permission(principal: Principal, permission_key: str) -> bool:
    return "*" in principal.permissions or permission_key in principal.permissions


def has_any_permission(principal: Principal, permission_keys: tuple[str, ...]) -> bool:
    return "*" in principal.permissions or any(
        permission_key in principal.permissions for permission_key in permission_keys
    )


def require_permission(permission_key: str) -> Callable[..., Principal]:
    if not permission_key or permission_key != permission_key.strip():
        raise ValueError("permission_key must be a non-empty canonical value")

    def dependency(
        principal: Annotated[Principal, Depends(require_principal)],
        request: Request = None,
    ) -> Principal:
        required_key = (
            permission_for_request(request.method, request.url.path, permission_key)
            if request is not None
            else permission_key
        )
        if has_permission(principal, required_key):
            return principal
        # Temporary compatibility for the preview principal and rolling deployment.
        if required_key != permission_key and has_permission(principal, permission_key):
            return principal
        raise ApiError(
            code=ErrorCode.FORBIDDEN,
            status_code=403,
            details={"required_permission": required_key},
        )

    return dependency


def require_any_permission(*permission_keys: str) -> Callable[..., Principal]:
    normalized = tuple(dict.fromkeys(permission_keys))
    if not normalized or any(not item or item != item.strip() for item in normalized):
        raise ValueError("permission_keys must contain canonical non-empty values")

    def dependency(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> Principal:
        if has_any_permission(principal, normalized):
            return principal
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    return dependency


def require_super_admin(
    principal: Annotated[Principal, Depends(require_principal)],
) -> Principal:
    if "*" in principal.permissions:
        return principal
    raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
