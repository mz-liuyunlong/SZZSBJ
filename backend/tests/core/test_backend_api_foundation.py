import logging
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import PUBLIC_ENDPOINT_PATHS, Principal, get_optional_principal
from app.core.data_scope import StoreDataScope, StoreScopeKind, resolve_store_scope
from app.core.permissions import require_permission
from app.main import create_app

VIEW_PERMISSION = "products.product_management.view"
PRODUCT_RESOURCE = "products.product_management"
OTHER_PERMISSION = "ads.dashboard.view"
OTHER_RESOURCE = "ads.dashboard"


def _principal(*permissions: str) -> Principal:
    return Principal(user_id="test-user", permissions=frozenset(permissions))


def _assert_request_id(response: Any) -> str:
    request_id = response.json()["request_id"]
    assert response.headers["X-Request-ID"] == request_id
    return str(request_id)


def _add_protected_route(application: FastAPI) -> None:
    @application.get("/protected")
    def protected(request: Request) -> SuccessEnvelope[dict[str, str], None]:
        return success_response(request, data={"status": "protected"}, meta=None)


def test_valid_request_id_is_preserved() -> None:
    response = TestClient(create_app()).get(
        "/health",
        headers={"X-Request-ID": "req.Valid_123:abc-DEF"},
    )

    assert response.status_code == 200
    assert _assert_request_id(response) == "req.Valid_123:abc-DEF"


@pytest.mark.parametrize(
    "unsafe_request_id",
    ["unsafe request id!", "   ", "a" * 129],
)
def test_unsafe_request_id_is_replaced(unsafe_request_id: str) -> None:
    response = TestClient(create_app()).get(
        "/health",
        headers={"X-Request-ID": unsafe_request_id},
    )

    assert response.status_code == 200
    request_id = _assert_request_id(response)
    UUID(request_id)
    assert unsafe_request_id not in response.text


def test_health_is_public_and_safe() -> None:
    response = TestClient(create_app()).get("/health")

    assert PUBLIC_ENDPOINT_PATHS == frozenset({"/health"})
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}
    assert set(response.json()) == {"success", "data", "error", "meta", "request_id"}
    assert "secret" not in response.text.lower()
    assert "connection" not in response.text.lower()


def test_error_code_model_accepts_module_extensions() -> None:
    error = ApiError(code="MODULE_SPECIFIC_ERROR", status_code=409)

    assert error.code == "MODULE_SPECIFIC_ERROR"
    assert error.message == "请求失败"


def test_unapproved_documentation_routes_are_not_public() -> None:
    client = TestClient(create_app())

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_unlisted_route_is_protected_by_default_and_override_is_temporary() -> None:
    application = create_app()
    _add_protected_route(application)
    client = TestClient(application)

    unauthorized = client.get("/protected")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == ErrorCode.UNAUTHORIZED
    _assert_request_id(unauthorized)

    application.dependency_overrides[get_optional_principal] = lambda: _principal()
    assert client.get("/protected").status_code == 200

    application.dependency_overrides.clear()
    assert client.get("/protected").status_code == 401


def test_permission_dependency_fails_closed_and_allows_matching_key() -> None:
    application = create_app()
    permission_dependency = require_permission(VIEW_PERMISSION)

    @application.get("/permission-protected")
    def permission_protected(
        request: Request,
        principal: Annotated[Principal, Depends(permission_dependency)],
    ) -> SuccessEnvelope[dict[str, str], None]:
        return success_response(request, data={"user_id": principal.user_id}, meta=None)

    client = TestClient(application)
    assert client.get("/permission-protected").status_code == 401

    application.dependency_overrides[get_optional_principal] = lambda: _principal()
    forbidden = client.get("/permission-protected")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == ErrorCode.FORBIDDEN

    application.dependency_overrides[get_optional_principal] = lambda: _principal(
        VIEW_PERMISSION
    )
    assert client.get("/permission-protected").status_code == 200
    application.dependency_overrides.clear()


def test_404_and_405_use_safe_envelopes() -> None:
    client = TestClient(create_app())

    not_found = client.get("/missing")
    assert not_found.status_code == 404
    not_found_body = not_found.json()
    assert not_found_body == {
        "success": False,
        "data": None,
        "error": {
            "code": ErrorCode.NOT_FOUND,
            "message": "资源不存在",
            "details": {},
        },
        "meta": None,
        "request_id": not_found_body["request_id"],
    }
    _assert_request_id(not_found)

    method_not_allowed = client.post("/health")
    assert method_not_allowed.status_code == 405
    assert method_not_allowed.json()["error"]["code"] == ErrorCode.METHOD_NOT_ALLOWED
    assert "GET" in method_not_allowed.headers["Allow"]
    _assert_request_id(method_not_allowed)


def test_other_client_http_error_keeps_status_without_detail() -> None:
    application = create_app()

    @application.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="sensitive internal detail")

    application.dependency_overrides[get_optional_principal] = lambda: _principal()
    response = TestClient(application).get("/teapot")

    assert response.status_code == 418
    assert response.json()["error"]["code"] == ErrorCode.INVALID_REQUEST
    assert "sensitive internal detail" not in response.text
    _assert_request_id(response)
    application.dependency_overrides.clear()


def test_validation_error_uses_safe_envelope() -> None:
    application = create_app()

    @application.get("/validated")
    def validated(request: Request, value: int) -> SuccessEnvelope[dict[str, int], None]:
        return success_response(request, data={"value": value}, meta=None)

    application.dependency_overrides[get_optional_principal] = lambda: _principal()
    response = TestClient(application).get("/validated", params={"value": "private-input"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["meta"] is None
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert "private-input" not in response.text
    _assert_request_id(response)
    application.dependency_overrides.clear()


def test_unknown_exception_is_hidden_and_safely_logged(caplog: pytest.LogCaptureFixture) -> None:
    application = create_app()

    @application.get("/explode")
    def explode() -> None:
        raise RuntimeError("sensitive database detail")

    application.dependency_overrides[get_optional_principal] = lambda: _principal()
    with caplog.at_level(logging.ERROR, logger="app.core.api"):
        response = TestClient(application, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == ErrorCode.INTERNAL_ERROR
    assert "sensitive database detail" not in response.text
    assert "sensitive database detail" not in caplog.text
    assert "RuntimeError" in caplog.text
    _assert_request_id(response)
    application.dependency_overrides.clear()


def test_same_principal_can_have_different_resource_scopes() -> None:
    principal = _principal(VIEW_PERMISSION, OTHER_PERMISSION)
    scopes = {
        (PRODUCT_RESOURCE, VIEW_PERMISSION): StoreDataScope.selected({"store-a"}),
        (OTHER_RESOURCE, OTHER_PERMISSION): StoreDataScope.selected({"store-b"}),
    }

    def provider(
        _: Principal,
        resource_key: str,
        permission_key: str,
    ) -> StoreDataScope | None:
        return scopes.get((resource_key, permission_key))

    product_scope = resolve_store_scope(
        principal=principal,
        resource_key=PRODUCT_RESOURCE,
        permission_key=VIEW_PERMISSION,
        requested_store_id=None,
        provider=provider,
    )
    other_scope = resolve_store_scope(
        principal=principal,
        resource_key=OTHER_RESOURCE,
        permission_key=OTHER_PERMISSION,
        requested_store_id=None,
        provider=provider,
    )

    assert product_scope.store_ids == frozenset({"store-a"})
    assert other_scope.store_ids == frozenset({"store-b"})


def test_selected_scope_only_allows_authorized_store() -> None:
    principal = _principal(VIEW_PERMISSION)

    def provider(_: Principal, __: str, ___: str) -> StoreDataScope:
        return StoreDataScope.selected({"store-a", "store-b"})

    narrowed = resolve_store_scope(
        principal=principal,
        resource_key=PRODUCT_RESOURCE,
        permission_key=VIEW_PERMISSION,
        requested_store_id="store-a",
        provider=provider,
    )
    assert narrowed.kind is StoreScopeKind.SELECTED
    assert narrowed.store_ids == frozenset({"store-a"})

    with pytest.raises(ApiError) as denied:
        resolve_store_scope(
            principal=principal,
            resource_key=PRODUCT_RESOURCE,
            permission_key=VIEW_PERMISSION,
            requested_store_id="store-c",
            provider=provider,
        )
    assert denied.value.code == ErrorCode.DATA_SCOPE_DENIED


def test_all_scope_requires_explicit_provider_grant() -> None:
    principal = _principal(VIEW_PERMISSION)

    def provider(_: Principal, __: str, ___: str) -> StoreDataScope:
        return StoreDataScope.all()

    with pytest.raises(ApiError) as missing_provider:
        resolve_store_scope(
            principal=principal,
            resource_key=PRODUCT_RESOURCE,
            permission_key=VIEW_PERMISSION,
            requested_store_id=None,
            provider=None,
        )
    assert missing_provider.value.code == ErrorCode.DATA_SCOPE_DENIED

    scope = resolve_store_scope(
        principal=principal,
        resource_key=PRODUCT_RESOURCE,
        permission_key=VIEW_PERMISSION,
        requested_store_id=None,
        provider=provider,
    )
    assert scope.kind is StoreScopeKind.ALL

    narrowed = resolve_store_scope(
        principal=principal,
        resource_key=PRODUCT_RESOURCE,
        permission_key=VIEW_PERMISSION,
        requested_store_id="store-a",
        provider=provider,
    )
    assert narrowed == StoreDataScope.selected({"store-a"})

    with pytest.raises(ApiError) as blank_store:
        resolve_store_scope(
            principal=principal,
            resource_key=PRODUCT_RESOURCE,
            permission_key=VIEW_PERMISSION,
            requested_store_id="",
            provider=provider,
        )
    assert blank_store.value.code == ErrorCode.DATA_SCOPE_DENIED


def test_unknown_or_none_resource_scope_fails_closed() -> None:
    principal = _principal(VIEW_PERMISSION)

    def provider(_: Principal, resource_key: str, __: str) -> StoreDataScope | None:
        if resource_key == PRODUCT_RESOURCE:
            return StoreDataScope.none()
        return None

    for resource_key in (PRODUCT_RESOURCE, "unknown.resource"):
        with pytest.raises(ApiError) as denied:
            resolve_store_scope(
                principal=principal,
                resource_key=resource_key,
                permission_key=VIEW_PERMISSION,
                requested_store_id=None,
                provider=provider,
            )
        assert denied.value.code == ErrorCode.DATA_SCOPE_DENIED


def test_scope_requires_matching_permission() -> None:
    with pytest.raises(ApiError) as denied:
        resolve_store_scope(
            principal=_principal(),
            resource_key=PRODUCT_RESOURCE,
            permission_key=VIEW_PERMISSION,
            requested_store_id=None,
            provider=lambda _principal, _resource, _permission: StoreDataScope.all(),
        )

    assert denied.value.code == ErrorCode.FORBIDDEN
