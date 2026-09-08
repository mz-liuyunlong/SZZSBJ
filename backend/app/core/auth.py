from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, Request

from app.core.api import ApiError, ErrorCode

PUBLIC_ENDPOINT_PATHS: Final[frozenset[str]] = frozenset({"/health"})


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    permissions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.user_id or self.user_id != self.user_id.strip():
            raise ValueError("user_id must be a non-empty canonical value")
        if any(not key or key != key.strip() for key in self.permissions):
            raise ValueError("permission keys must be non-empty canonical values")


def get_optional_principal() -> Principal | None:
    """Trusted authentication provider entrypoint; fail closed until integrated."""
    return None


def require_principal(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> Principal:
    if principal is None:
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
    return principal


def enforce_protected_by_default(
    request: Request,
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> None:
    if request.scope.get("path") in PUBLIC_ENDPOINT_PATHS:
        return
    if principal is None:
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
