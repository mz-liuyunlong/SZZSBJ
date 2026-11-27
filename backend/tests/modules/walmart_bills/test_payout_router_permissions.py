"""回款对账接口的权限：看 / 初审 / 终审 / 跟进分开授权。不需要数据库（服务层打桩）。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.walmart_bills import payout_router
from app.modules.walmart_bills.payout_schemas import (
    PayoutAutoMatchData,
    PayoutPeriodListData,
    PayoutReviewData,
)
from app.modules.walmart_bills.payout_service import PayoutReconError

READ = "page:finance:settlement-reconciliation:view"
REVIEW1 = "action:finance:settlement-reconciliation:review1"
REVIEW2 = "action:finance:settlement-reconciliation:review2"
FOLLOW = "action:finance:settlement-reconciliation:follow"
BASE = "/api/finance/payout-recon"
MATCH_ID = "00000000-0000-0000-0000-000000000001"
KEY = {"store_id": "900000000000000001", "report_key": "synthetic-key"}


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


class FakeService:
    calls: list[tuple[str, object]] = []

    def __init__(self, session) -> None:
        del session

    def list_periods(self, **kwargs):
        FakeService.calls.append(("list", kwargs))
        return PayoutPeriodListData(
            items=[], today=date(2026, 11, 10), recon_start=date(2026, 10, 1)
        )

    def auto_match(self, *, actor: str, request_id):
        FakeService.calls.append(("auto", actor))
        return PayoutAutoMatchData(matched_periods=0, matched_lines=0)

    def review(self, payload, *, actor: str, request_id):
        FakeService.calls.append(("review", payload.kind))
        return PayoutReviewData(done=1, skipped=[])

    def unmatch(self, match_id: UUID, *, reason: str, actor: str, request_id):
        raise PayoutReconError(409, "PAYOUT_RECON_STAGE_NOT_ALLOWED", "已初审")


@pytest.fixture(autouse=True)
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeService.calls = []
    monkeypatch.setattr(payout_router, "PayoutReconService", FakeService)


def user(*permissions: str) -> Principal:
    return Principal(user_id="u1", permissions=frozenset(permissions))


ENDPOINTS = [
    ("GET", f"{BASE}/periods", None),
    ("GET", f"{BASE}/accounts", None),
    ("GET", f"{BASE}/lines", None),
    ("POST", f"{BASE}/auto-match", None),
    ("POST", f"{BASE}/reviews", {"kind": "review1_pass", "periods": [KEY]}),
    ("POST", f"{BASE}/follow-ups", {**KEY, "content": "合成跟进"}),
    ("POST", f"{BASE}/matches/{MATCH_ID}/undo", {"reason": "合成原因"}),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_anonymous_gets_401(client_for, method: str, path: str, body) -> None:
    assert client_for(None).request(method, path, json=body).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_other_finance_users_get_403(client_for, method: str, path: str, body) -> None:
    other = user("page:finance:cash-flow:view")
    assert client_for(other).request(method, path, json=body).status_code == 403


def test_page_permission_reads_but_cannot_write(client_for) -> None:
    client = client_for(user(READ))
    assert client.get(f"{BASE}/periods").status_code == 200
    assert client.post(f"{BASE}/auto-match").status_code == 403
    review = client.post(f"{BASE}/reviews", json={"kind": "review1_pass", "periods": [KEY]})
    assert review.status_code == 403
    assert client.post(f"{BASE}/follow-ups", json={**KEY, "content": "x"}).status_code == 403


def test_review1_cannot_do_final_review(client_for) -> None:
    client = client_for(user(READ, REVIEW1))
    first = client.post(f"{BASE}/reviews", json={"kind": "review1_pass", "periods": [KEY]})
    assert (first.status_code, first.json()["data"]["done"]) == (200, 1)
    final = client.post(f"{BASE}/reviews", json={"kind": "review2_pass", "periods": [KEY]})
    assert final.status_code == 403
    assert client.post(f"{BASE}/auto-match").status_code == 200
    assert FakeService.calls == [("review", "review1_pass"), ("auto", "u1")]


def test_review2_can_pass_and_reject(client_for) -> None:
    client = client_for(user(READ, REVIEW2))
    for kind in ("review2_pass", "review2_reject"):
        body = {"kind": kind, "periods": [KEY], "reason": "合成原因"}
        assert client.post(f"{BASE}/reviews", json=body).status_code == 200
    assert client.post(f"{BASE}/auto-match").status_code == 403


def test_service_errors_map_to_their_status(client_for) -> None:
    client = client_for(user(READ, REVIEW1))
    undo = client.post(f"{BASE}/matches/{MATCH_ID}/undo", json={"reason": "合成原因"})
    assert (undo.status_code, undo.json()["error"]["code"]) == (
        409,
        "PAYOUT_RECON_STAGE_NOT_ALLOWED",
    )


def test_bad_input_is_422(client_for) -> None:
    client = client_for(user("*"))
    assert client.get(f"{BASE}/periods?store_id=abc").status_code == 422
    assert (
        client.get(
            f"{BASE}/periods?report_date_from=2026-10-20&report_date_to=2026-10-01"
        ).status_code
        == 422
    )
    bad_kind = client.post(f"{BASE}/reviews", json={"kind": "delete", "periods": [KEY]})
    assert bad_kind.status_code == 422
    empty = client.post(f"{BASE}/reviews", json={"kind": "review1_pass", "periods": []})
    assert empty.status_code == 422
