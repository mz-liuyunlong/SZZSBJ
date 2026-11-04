from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.api import ApiError, ErrorCode
from app.core.auth import (
    WALMART_MONITOR_TARGETS_PATH,
    WALMART_MONITOR_TARGETS_PRINCIPAL_ID,
    WALMART_MONITOR_TARGETS_READ_PERMISSION,
    Principal,
    require_principal,
)

# Explicit compatibility aliases for grants created before canonical RBAC v2 keys.
# Aliases are one-way and operation-specific: read grants never imply write grants.
_LEGACY_PERMISSION_ALIASES: dict[str, frozenset[str]] = {
    "page:pmc:purchase-board:view": frozenset({"pmc:purchase:read"}),
    "action:pmc:purchase-board:override": frozenset({"pmc:purchase:override"}),
}


def has_permission(principal: Principal, permission_key: str) -> bool:
    from app.modules.iam.permission_catalog_v2 import register_runtime_permission_key

    register_runtime_permission_key(permission_key)
    if "*" in principal.permissions or permission_key in principal.permissions:
        return True
    return bool(_LEGACY_PERMISSION_ALIASES.get(permission_key, frozenset()) & principal.permissions)


def has_any_permission(principal: Principal, permission_keys: tuple[str, ...]) -> bool:
    from app.modules.iam.permission_catalog_v2 import register_runtime_permission_key

    for permission_key in permission_keys:
        register_runtime_permission_key(permission_key)
    return "*" in principal.permissions or any(
        permission_key in principal.permissions for permission_key in permission_keys
    )


def require_permission(permission_key: str) -> Callable[..., Principal]:
    from app.modules.iam.permission_catalog_v2 import register_runtime_permission_key

    if not permission_key or permission_key != permission_key.strip():
        raise ValueError("permission_key must be a non-empty canonical value")
    register_runtime_permission_key(permission_key)

    def dependency(
        principal: Annotated[Principal, Depends(require_principal)],
        request: Request = None,
    ) -> Principal:
        from app.core.permission_policy_v2 import permission_for_request

        required_key = (
            permission_for_request(request.method, request.url.path, permission_key)
            if request is not None
            else permission_key
        )
        if has_permission(principal, required_key):
            return principal
        # Only the fixed read-only machine endpoint may accept its historical
        # dedicated token permission. Never alias it to the entire monitor page.
        if (
            request is not None
            and request.method == "GET"
            and request.url.path == WALMART_MONITOR_TARGETS_PATH
            and permission_key == WALMART_MONITOR_TARGETS_READ_PERMISSION
            and principal.user_id == WALMART_MONITOR_TARGETS_PRINCIPAL_ID
            and has_permission(principal, WALMART_MONITOR_TARGETS_READ_PERMISSION)
        ):
            return principal
        raise ApiError(
            code=ErrorCode.FORBIDDEN,
            status_code=403,
            details={"required_permission": required_key},
        )

    return dependency


def require_any_permission(*permission_keys: str) -> Callable[..., Principal]:
    from app.modules.iam.permission_catalog_v2 import register_runtime_permission_key

    normalized = tuple(dict.fromkeys(permission_keys))
    if not normalized or any(not item or item != item.strip() for item in normalized):
        raise ValueError("permission_keys must contain canonical non-empty values")
    for permission_key in normalized:
        register_runtime_permission_key(permission_key)

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
