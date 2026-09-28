import secrets
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, Request
from pydantic import SecretStr

from app.core.api import ApiError, ErrorCode
from app.core.config import SettingsError, get_settings

PUBLIC_ENDPOINT_PATHS: Final[frozenset[str]] = frozenset({"/health"})
PUBLIC_GET_ENDPOINT_PREFIXES: Final[frozenset[str]] = frozenset({"/api/media/image-assets/"})
PREVIEW_AUTH_HEADER: Final = "X-Product-Management-Preview-Token"
PREVIEW_PRINCIPAL_ID: Final = "frontend-preview"
_PREVIEW_PERMISSIONS: Final = frozenset(
    {
        "products:read",
        "products:pricing_rules:read",
        "products:cost:read",
        "integrations:read",
        "sales:daily-sales:read",
        "aftersales:refund-management:read",
        "warehouse:wfs-fee-alert:read",
        "business-rules:read",
        "business-rules:write",
        "business-rules:execute",
        "pmc:purchase:read",
        "operations:plan:read",
        "operations:plan:write",
    }
)
_PREVIEW_PATH_PREFIXES: Final = frozenset(
    {
        "/api/product-management/",
        "/api/data-pages/",
        "/api/sales/",
        "/api/after-sales/",
        "/api/listings/",
        "/api/warehouse/",
        "/api/business-rules/",
        "/api/pmc/",
        "/api/operations/",
        "/api/operations/plans/",
    }
)
_PREVIEW_READ_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/user-table-views/product-management",
        "/api/integrations/interfaces",
        "/api/integrations/sync-configs",
        "/api/integrations/sync-runs",
    }
)
_PREVIEW_WRITE_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/business-rules/store-commissions",
        "/api/business-rules/store-commissions/deactivate",
        "/api/business-rules/store-commissions/recalculate",
        "/api/operations/plans/import",
    }
)
_PREVIEW_WRITE_PATH_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "/api/operations/plans/products/",
    }
)
_PREVIEW_WRITE_METHODS: Final[frozenset[str]] = frozenset({"POST", "PATCH"})


def _constant_time_ascii_equals(provided: str, expected: SecretStr) -> bool:
    try:
        provided_bytes = provided.encode("ascii")
        expected_bytes = expected.get_secret_value().encode("ascii")
        return secrets.compare_digest(provided_bytes, expected_bytes)
    except (UnicodeEncodeError, TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    permissions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.user_id or self.user_id != self.user_id.strip():
            raise ValueError("user_id must be a non-empty canonical value")
        if any(not key or key != key.strip() for key in self.permissions):
            raise ValueError("permission keys must be non-empty canonical values")


def get_optional_principal(request: Request) -> Principal | None:
    """Return the temporary preview principal or fail closed."""
    path = request.scope.get("path")
    path_allowed = isinstance(path, str) and (
        any(path.startswith(prefix) for prefix in _PREVIEW_PATH_PREFIXES)
        or path in _PREVIEW_READ_PATHS
    )
    write_allowed = (
        request.method in _PREVIEW_WRITE_METHODS
        and isinstance(path, str)
        and (
            path in _PREVIEW_WRITE_PATHS
            or any(path.startswith(prefix) for prefix in _PREVIEW_WRITE_PATH_PREFIXES)
        )
    )
    operation_plan_mutation_allowed = (
        request.method in {"POST", "PATCH"}
        and isinstance(path, str)
        and path.startswith("/api/operations/plans/")
    )
    if not (
        (request.method == "GET" and path_allowed)
        or write_allowed
        or operation_plan_mutation_allowed
    ):
        return None
    try:
        settings = get_settings()
    except SettingsError:
        return None
    configured = settings.product_management_preview_auth_token
    supplied = request.headers.get(PREVIEW_AUTH_HEADER)
    if (
        not settings.product_management_preview_auth_configured
        or configured is None
        or supplied is None
    ):
        return None
    if not _constant_time_ascii_equals(supplied, configured):
        return None
    return Principal(user_id=PREVIEW_PRINCIPAL_ID, permissions=_PREVIEW_PERMISSIONS)


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
    path = request.scope.get("path")
    if path in PUBLIC_ENDPOINT_PATHS:
        return
    if (
        request.method == "GET"
        and isinstance(path, str)
        and any(path.startswith(prefix) for prefix in PUBLIC_GET_ENDPOINT_PREFIXES)
    ):
        return
    if principal is None:
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
