from collections.abc import Iterator
from secrets import token_urlsafe
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.auth import (
    PREVIEW_AUTH_HEADER,
    PREVIEW_PRINCIPAL_ID,
    Principal,
    get_optional_principal,
)
from app.core.config import Settings, SettingsError, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.integration_sync.schemas import (
    InterfaceListData,
    SyncConfigListData,
    SyncRunListData,
)
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.product_management.schemas import (
    PricingRulesData,
    ProductManagementListData,
    ProductManagementOptionsData,
)
from app.modules.product_management.service import ProductManagementService
from app.modules.products.dependencies import get_product_scope_provider

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
PREVIEW_ENV_NAMES = (
    "PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED",
    "PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN",
    "PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS",
)


@pytest.fixture(autouse=True)
def reset_preview_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in PREVIEW_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _enable_preview(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_account_refs: str | None = None,
) -> str:
    token = token_urlsafe(32)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED", "true")
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN", token)
    if source_account_refs is not None:
        monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS", source_account_refs)
    get_settings.cache_clear()
    return token


def _app() -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _empty_options(
    _: ProductManagementService,
    __: frozenset[str],
    _query: object | None = None,
) -> ProductManagementOptionsData:
    return ProductManagementOptionsData(
        product_grades=[],
        calculation_statuses=[],
        internal_tags=[],
    )


def test_preview_settings_default_closed_and_mask_token() -> None:
    defaults = Settings.model_validate(
        {"APP_ENV": "test", "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL}
    )
    assert defaults.product_management_preview_auth_enabled is False
    assert defaults.product_management_preview_auth_token is None
    assert defaults.product_management_preview_source_account_refs is None

    token = token_urlsafe(32)
    configured = Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED": True,
            "PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN": token,
        }
    )
    assert isinstance(configured.product_management_preview_auth_token, SecretStr)
    assert token not in repr(configured)
    assert token not in repr(configured.model_dump())
    assert token not in configured.model_dump_json()


@pytest.mark.parametrize(
    "invalid_token",
    ("synthetic-short-preview-token", "a" * 31 + "é"),
)
def test_invalid_preview_token_is_unusable_without_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    invalid_token: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED", "true")
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN", invalid_token)
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS", "acct-a")
    get_settings.cache_clear()

    with pytest.raises(SettingsError) as exc_info:
        get_settings()
    assert invalid_token not in str(exc_info.value)

    response = TestClient(_app()).get(
        "/api/product-management/options",
        headers=[(PREVIEW_AUTH_HEADER.encode(), invalid_token.encode())],
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert invalid_token not in response.text


def test_preview_auth_default_missing_and_wrong_header_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductManagementService, "options", _empty_options)
    app = _app()
    client = TestClient(app)
    token = token_urlsafe(32)

    assert client.get("/api/product-management/options").status_code == 401
    assert (
        client.get(
            "/api/product-management/options",
            headers={PREVIEW_AUTH_HEADER: token},
        ).status_code
        == 401
    )
    assert client.get("/health").status_code == 200

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    assert (
        client.get(
            "/api/product-management/options",
            headers={PREVIEW_AUTH_HEADER: token},
        ).status_code
        == 401
    )

    configured_token = _enable_preview(monkeypatch)
    assert client.get("/api/product-management/options").status_code == 401
    wrong = client.get(
        "/api/product-management/options",
        headers={PREVIEW_AUTH_HEADER: token_urlsafe(32)},
    )
    assert wrong.status_code == 401
    assert configured_token not in wrong.text


def test_non_ascii_wrong_preview_header_returns_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductManagementService, "options", _empty_options)
    configured_token = _enable_preview(monkeypatch, source_account_refs="acct-a")
    provided_header = "错误的非ASCIItoken"

    response = TestClient(_app()).get(
        "/api/product-management/options",
        headers=[(PREVIEW_AUTH_HEADER.encode(), provided_header.encode())],
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert provided_header not in response.text
    assert configured_token not in response.text


def test_correct_preview_token_creates_only_the_approved_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _enable_preview(monkeypatch)
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/product-management/options",
        "headers": [(PREVIEW_AUTH_HEADER.lower().encode(), token.encode())],
    }

    principal = get_optional_principal(Request(scope))

    assert principal == Principal(
        user_id=PREVIEW_PRINCIPAL_ID,
        permissions=frozenset(
            {
                "products:read",
                "products:pricing_rules:read",
                "products:cost:read",
                "integrations:read",
                "sales:daily-sales:read",
                "warehouse:wfs-fee-alert:read",
            }
        ),
    )
    assert "products:export" not in principal.permissions


def test_correct_preview_token_is_path_bound_and_export_remains_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductManagementService, "options", _empty_options)
    token = _enable_preview(monkeypatch, source_account_refs="acct-a, acct-b,acct-a")
    client = TestClient(_app())
    headers = {PREVIEW_AUTH_HEADER: token}

    options = client.get("/api/product-management/options", headers=headers)
    outside_scope = client.get("/api/v1/products", headers=headers)
    export = client.post("/api/product-management/skus/export", headers=headers, json={})
    table_view_write = client.put(
        "/api/user-table-views/product-management",
        headers=headers,
        json={},
    )

    assert options.status_code == 200
    assert token not in options.text
    assert outside_scope.status_code == 401
    assert export.status_code == 401
    assert export.json()["error"]["code"] == "UNAUTHORIZED"
    assert table_view_write.status_code == 401
    assert table_view_write.json()["error"]["code"] == "UNAUTHORIZED"


def test_preview_token_allows_only_the_three_integration_list_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        IntegrationSyncService,
        "list_interfaces",
        MagicMock(return_value=(InterfaceListData(items=[]), 0)),
    )
    monkeypatch.setattr(
        IntegrationSyncService,
        "list_configs",
        MagicMock(return_value=(SyncConfigListData(items=[]), 0)),
    )
    monkeypatch.setattr(
        IntegrationSyncService,
        "list_runs",
        MagicMock(return_value=(SyncRunListData(items=[]), 0)),
    )
    token = _enable_preview(monkeypatch, source_account_refs="acct-a")
    client = TestClient(_app())
    headers = {PREVIEW_AUTH_HEADER: token}

    for path in (
        "/api/integrations/interfaces",
        "/api/integrations/sync-configs",
        "/api/integrations/sync-runs",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert token not in response.text


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("PATCH", "/api/integrations/sync-configs/00000000-0000-0000-0000-000000000001"),
        ("POST", "/api/integrations/sync-configs/00000000-0000-0000-0000-000000000001/run"),
        ("POST", "/api/integrations/sync-runs/00000000-0000-0000-0000-000000000001/retry"),
        ("POST", "/api/integrations/sync-configs/00000000-0000-0000-0000-000000000001/backfill"),
    ),
)
def test_preview_token_does_not_authorize_integration_writes(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    token = _enable_preview(monkeypatch, source_account_refs="acct-a")

    response = TestClient(_app()).request(
        method,
        path,
        headers={PREVIEW_AUTH_HEADER: token},
        json={},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert token not in response.text


def test_preview_product_scope_only_allows_expected_principal_and_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_preview(monkeypatch, source_account_refs="acct-a")
    provider = get_product_scope_provider()
    assert provider is not None

    preview = Principal(user_id=PREVIEW_PRINCIPAL_ID)
    other = Principal(user_id="synthetic-user")
    assert provider(preview, "product_management") is True
    assert provider(other, "product_management") is False
    assert provider(preview, "other_resource") is False


def test_preview_source_account_scope_parses_and_rejects_other_principals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = Settings.model_validate(
        {"APP_ENV": "test", "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL}
    )
    parsed = Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS": "acct-a, acct-b,acct-a, ,",
        }
    )
    assert empty.product_management_preview_source_account_ref_set == frozenset()
    assert parsed.product_management_preview_source_account_ref_set == frozenset(
        {"acct-a", "acct-b"}
    )

    _enable_preview(monkeypatch, source_account_refs="acct-a, acct-b,acct-a")
    provider = get_source_account_scope_provider()
    assert provider is not None
    assert provider(Principal(user_id=PREVIEW_PRINCIPAL_ID)) == frozenset({"acct-a", "acct-b"})
    assert provider(Principal(user_id="synthetic-user")) == frozenset()


def test_missing_source_account_scope_denies_all_preview_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductManagementService, "options", _empty_options)
    token = _enable_preview(monkeypatch)
    client = TestClient(_app())
    headers = {PREVIEW_AUTH_HEADER: token}

    options = client.get("/api/product-management/options", headers=headers)
    denied = client.get("/api/product-management/skus", headers=headers)
    assert options.status_code == 403
    assert options.json()["error"]["code"] == "DATA_SCOPE_DENIED"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "DATA_SCOPE_DENIED"
    assert token not in denied.text


def test_configured_source_scope_allows_read_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def list_skus(
        _: ProductManagementService,
        query: Any,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> tuple[ProductManagementListData, int, None, None]:
        captured["list_scope"] = account_refs
        return ProductManagementListData(items=[]), 0, None, None

    def list_rules(
        _: ProductManagementService,
        source_account_ref: str,
        account_refs: frozenset[str],
    ) -> PricingRulesData:
        captured["rule_scope"] = account_refs
        return PricingRulesData(items=[], active_rule_id=None)

    monkeypatch.setattr(ProductManagementService, "list_skus", list_skus)
    monkeypatch.setattr(ProductManagementService, "list_rules", list_rules)
    token = _enable_preview(monkeypatch, source_account_refs="acct-a, acct-b,acct-a")
    client = TestClient(_app())
    headers = {PREVIEW_AUTH_HEADER: token}

    listed = client.get("/api/product-management/skus", headers=headers)
    rules = client.get(
        "/api/product-management/pricing-rules",
        headers=headers,
        params={"source_account_ref": "acct-a"},
    )

    assert listed.status_code == 200
    assert rules.status_code == 200
    assert captured == {
        "list_scope": frozenset({"acct-a", "acct-b"}),
        "rule_scope": frozenset({"acct-a", "acct-b"}),
    }
    assert token not in listed.text
    assert token not in rules.text
