from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Never, Self

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal


class StoreScopeKind(StrEnum):
    ALL = "ALL"
    SELECTED = "SELECTED"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class StoreDataScope:
    kind: StoreScopeKind
    store_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.kind is StoreScopeKind.SELECTED and not self.store_ids:
            raise ValueError("SELECTED scope requires store_ids")
        if self.kind is not StoreScopeKind.SELECTED and self.store_ids:
            raise ValueError("only SELECTED scope may contain store_ids")
        if any(not store_id or store_id != store_id.strip() for store_id in self.store_ids):
            raise ValueError("store_ids must be non-empty canonical values")

    @classmethod
    def all(cls) -> Self:
        return cls(StoreScopeKind.ALL)

    @classmethod
    def selected(cls, store_ids: Iterable[str]) -> Self:
        return cls(StoreScopeKind.SELECTED, frozenset(store_ids))

    @classmethod
    def none(cls) -> Self:
        return cls(StoreScopeKind.NONE)


type StoreScopeProvider = Callable[
    [Principal, str, str],
    StoreDataScope | None,
]


def get_store_scope_provider() -> StoreScopeProvider | None:
    """Trusted resource-level scope provider entrypoint; absent by default."""
    return None


def resolve_store_scope(
    *,
    principal: Principal,
    resource_key: str,
    permission_key: str,
    requested_store_id: str | None,
    provider: StoreScopeProvider | None,
) -> StoreDataScope:
    if not resource_key or resource_key != resource_key.strip():
        _deny_scope()
    if not permission_key or permission_key != permission_key.strip():
        _deny_scope()
    if permission_key not in principal.permissions:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    if requested_store_id is not None and (
        not requested_store_id or requested_store_id != requested_store_id.strip()
    ):
        _deny_scope()
    if provider is None:
        _deny_scope()

    scope = provider(principal, resource_key, permission_key)
    if scope is None or scope.kind is StoreScopeKind.NONE:
        _deny_scope()
    if scope.kind is StoreScopeKind.ALL:
        return StoreDataScope.selected({requested_store_id}) if requested_store_id else scope
    if requested_store_id is None:
        return scope
    if requested_store_id not in scope.store_ids:
        _deny_scope()
    return StoreDataScope.selected({requested_store_id})


def _deny_scope() -> Never:
    raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
