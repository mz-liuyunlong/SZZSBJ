"""WFS 费用接口的权限：看要页面权限，导入 / 调整要各自的动作权限。不需要数据库。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.wfs_fees import router as wfs_router

READ = "page:finance:wfs-fees:view"
IMPORT = "action:finance:wfs-fees:import"
ADJUST = "action:finance:wfs-fees:adjust"
LINE = uuid4()
ENDPOINTS = [
    ("GET", "/api/finance/wfs-fees/fee-types"),
    ("GET", "/api/finance/wfs-fees/periods"),
    ("GET", "/api/finance/wfs-fees/lines"),
    ("GET", "/api/finance/wfs-fees/summary"),
    ("GET", "/api/finance/wfs-fees/checks"),
    ("GET", "/api/finance/wfs-fees/files"),
    ("POST", "/api/finance/wfs-fees/imports"),
    ("POST", f"/api/finance/wfs-fees/lines/{LINE}/adjust"),
    ("POST", "/api/finance/wfs-fees/checks/verify"),
]


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TestClient]]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    get_settings.cache_clear()

    def build(principal: Principal | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_optional_principal] = lambda: principal
        app.dependency_overrides[get_db_session] = lambda: MagicMock()
        return TestClient(app, raise_server_exceptions=False)

    yield build
    get_settings.cache_clear()


def user(*permissions: str) -> Principal:
    return Principal(user_id="u1", permissions=frozenset(permissions))


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_anonymous_gets_401(client_for, method: str, path: str) -> None:
    assert client_for(None).request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_other_finance_users_get_403(client_for, method: str, path: str) -> None:
    assert client_for(user("page:finance:cash-flow:view")).request(method, path).status_code == 403


def test_view_permission_reads_but_cannot_import_or_adjust(client_for, monkeypatch) -> None:
    monkeypatch.setattr(wfs_router.reader, "list_lines", lambda *a, **k: ([], 0))
    monkeypatch.setattr(wfs_router.reader, "list_checks", lambda *a, **k: [])
    monkeypatch.setattr(wfs_router.reader, "list_periods", lambda *a, **k: [])
    client = client_for(user(READ))
    assert client.get("/api/finance/wfs-fees/fee-types").status_code == 200
    assert client.get("/api/finance/wfs-fees/lines").json()["data"]["total"] == 0
    assert client.get("/api/finance/wfs-fees/checks").status_code == 200
    assert client.get("/api/finance/wfs-fees/periods").json()["data"]["items"] == []
    assert client.post("/api/finance/wfs-fees/imports", content=b"x").status_code == 403
    assert (
        client.post(
            f"/api/finance/wfs-fees/lines/{LINE}/adjust", json={"kind": "company", "reason": "r"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/finance/wfs-fees/checks/verify",
            json={"store_id": "1", "report_key": "k", "fee_type": "t", "reason": "r"},
        ).status_code
        == 403
    )


def test_import_permission_rejects_empty_and_oversized_bodies(client_for) -> None:
    client = client_for(user(IMPORT))
    assert client.post("/api/finance/wfs-fees/imports", content=b"").status_code == 422
    too_big = client.post(
        "/api/finance/wfs-fees/imports",
        content=b"x",
        headers={"content-length": str(20 * 1024 * 1024)},
    )
    assert too_big.status_code == 413


def test_adjust_validation(client_for) -> None:
    client = client_for(user(ADJUST))
    assert (
        client.post(
            f"/api/finance/wfs-fees/lines/{LINE}/adjust", json={"kind": "verified", "reason": "r"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/finance/wfs-fees/lines/{LINE}/adjust", json={"kind": "company", "reason": ""}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/finance/wfs-fees/checks/verify",
            json={"store_id": "abc", "report_key": "k", "fee_type": "t", "reason": "r"},
        ).status_code
        == 422
    )