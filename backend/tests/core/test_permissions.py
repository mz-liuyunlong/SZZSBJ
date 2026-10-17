import pytest
from fastapi import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.core.permissions import require_permission


def test_require_permission_allows_exact_permission() -> None:
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )

    resolved = require_permission("products:read")(principal)

    assert resolved is principal


def test_require_permission_allows_super_permission_marker() -> None:
    principal = Principal(
        user_id="synthetic-admin",
        permissions=frozenset({"*"}),
    )

    resolved = require_permission("products:read")(principal)

    assert resolved is principal


def test_require_permission_rejects_missing_permission() -> None:
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset({"sales:daily-sales:read"}),
    )

    with pytest.raises(ApiError):
        require_permission("products:read")(principal)


def test_legacy_permission_cannot_bypass_canonical_request_action() -> None:
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/listings/tags",
            "headers": [],
        }
    )

    with pytest.raises(ApiError) as exc_info:
        require_permission("products:read")(principal, request)

    assert exc_info.value.status_code == 403
