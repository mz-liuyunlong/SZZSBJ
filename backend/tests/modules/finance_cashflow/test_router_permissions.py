"""权限和上传限制：只有超级管理员能用；不需要数据库。"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app

UID = "0123456789abcdef"
IMPORT_ID = "00000000-0000-0000-0000-0000000000a1"
ENDPOINTS = [
    ("POST", "/api/finance/cashflow/imports"),
    ("GET", "/api/finance/cashflow/imports"),
    ("GET", f"/api/finance/cashflow/imports/{IMPORT_ID}"),
    ("POST", f"/api/finance/cashflow/imports/{IMPORT_ID}/void"),
    ("GET", "/api/finance/cashflow/accounts"),
    ("GET", "/api/finance/cashflow/categories"),
    ("GET", "/api/finance/cashflow/lines"),
    ("GET", "/api/finance/cashflow/anomalies"),
    ("POST", f"/api/finance/cashflow/lines/{UID}/events"),
]


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    monkeypatch.setenv("FINANCE_CASHFLOW_MAX_UPLOAD_BYTES", "10")
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    get_settings.cache_clear()

    def build(principal: Principal | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_optional_principal] = lambda: principal
        app.dependency_overrides[get_db_session] = lambda: MagicMock()
        return TestClient(app, raise_server_exceptions=False)

    yield build
    get_settings.cache_clear()


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_anonymous_gets_401(client_for, method, path):
    assert client_for(None).request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_other_users_get_403_even_with_finance_page_permission(client_for, method, path):
    finance_user = Principal(
        user_id="u1", permissions=frozenset({"page:finance:cash-flow:view", "finance:read"})
    )
    assert client_for(finance_user).request(method, path).status_code == 403


def super_admin() -> Principal:
    return Principal(user_id="admin", permissions=frozenset({"*"}))


def test_upload_over_limit_is_413(client_for):
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/imports", content=b"x" * 11, headers={"X-File-Name": "a.xlsx"}
    )
    assert response.status_code == 413


def test_empty_upload_is_422(client_for):
    response = client_for(super_admin()).post("/api/finance/cashflow/imports", content=b"")
    assert response.status_code == 422


def test_upload_without_storage_root_is_503_and_writes_nothing(client_for):
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/imports", content=b"abc", headers={"X-File-Name": "a.xlsx"}
    )
    assert response.status_code == 503


def test_default_upload_limit_is_20_mb(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    monkeypatch.delenv("FINANCE_CASHFLOW_MAX_UPLOAD_BYTES", raising=False)
    get_settings.cache_clear()
    assert get_settings().finance_cashflow_max_upload_bytes == 20 * 1024 * 1024
    get_settings.cache_clear()
