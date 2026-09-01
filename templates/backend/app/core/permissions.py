from __future__ import annotations

from collections.abc import Callable, Awaitable
from functools import wraps
from typing import Any

from fastapi import HTTPException, status


class CurrentUserProtocol:
    id: str
    permission_keys: set[str]


def has_permission(user: CurrentUserProtocol, permission_key: str) -> bool:
    return permission_key in user.permission_keys


def require_permission(permission_key: str):
    """Decorator template.

    Real project implementation should integrate with FastAPI dependencies.
    Never check role names here. Only check permissionKey.
    """

    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            user = kwargs.get("current_user")
            if user is None or not has_permission(user, permission_key):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
            return await func(*args, **kwargs)

        return wrapper

    return decorator
