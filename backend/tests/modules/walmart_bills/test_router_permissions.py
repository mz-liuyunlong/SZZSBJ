"""沃尔玛账单接口的权限：看要回款对账页面权限，手动同步要单独的动作权限。不需要数据库。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.walmart_bills import router as bills_router
from app.modules.walmart_bills.schemas import WalmartBillSyncData
from app.modules.walmart_bills.sync import (
    WalmartBillSyncNotConfiguredError,
    WalmartBillSyncUnavailableError,
)

READ = "page:finance:settlement-reconciliation:view"
SYNC = "action:finance:settlement-reconciliation:sync"
ENDPOINTS = [
    ("GET", "/api/finance/walmart-bills/periods"),
    ("GET", "/api/finance/walmart-bills/sync"),
    ("POST", "/api/finance/walmart-bills/sync"),
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
def test_users_without_finance_permissions_get_403(client_for, method: str, path: str) -> None:
    other = user("page:finance:cash-flow:view")
    assert client_for(other).request(method, path).status_code == 403


def test_page_permission_can_read_but_not_sync(client_for, monkeypatch) -> None:
    monkeypatch.setattr(bills_router, "list_periods", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        bills_router, "latest_walmart_bill_sync", lambda session: WalmartBillSyncData()
    )
    client = client_for(user(READ))
    periods = client.get("/api/finance/walmart-bills/periods")
    assert periods.status_code == 200
    assert periods.json()["data"] == {"items": []}
    assert client.get("/api/finance/walmart-bills/sync").json()["data"]["status"] == "never"
    assert client.post("/api/finance/walmart-bills/sync").status_code == 403


def test_sync_permission_starts_a_run_and_maps_errors(client_for, monkeypatch) -> None:
    outcomes: list[object] = [
        WalmartBillSyncData(status="queued"),
        WalmartBillSyncNotConfiguredError(),
        WalmartBillSyncUnavailableError(),
    ]

    def start(session, *, actor: str, request_id: str) -> WalmartBillSyncData:
        assert actor == "u1"
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, WalmartBillSyncData)
        return outcome

    monkeypatch.setattr(bills_router, "start_walmart_bill_sync", start)
    client = client_for(user(SYNC))
    first = client.post("/api/finance/walmart-bills/sync")
    assert (first.status_code, first.json()["data"]["status"]) == (202, "queued")
    off = client.post("/api/finance/walmart-bills/sync")
    assert (off.status_code, off.json()["error"]["code"]) == (
        409,
        "WALMART_BILL_SYNC_NOT_CONFIGURED",
    )
    down = client.post("/api/finance/walmart-bills/sync")
    assert (down.status_code, down.json()["error"]["code"]) == (
        503,
        "WALMART_BILL_SYNC_UNAVAILABLE",
    )


def test_super_admin_wildcard_can_do_everything(client_for, monkeypatch) -> None:
    monkeypatch.setattr(bills_router, "list_periods", lambda *args, **kwargs: [])
    assert client_for(user("*")).get("/api/finance/walmart-bills/periods").status_code == 200


def test_bad_query_is_422(client_for) -> None:
    client = client_for(user(READ))
    assert client.get("/api/finance/walmart-bills/periods?store_id=abc").status_code == 422
    reversed_range = (
        "/api/finance/walmart-bills/periods?report_date_from=2026-10-02&report_date_to=2026-10-01"
    )
    assert client.get(reversed_range).status_code == 422
