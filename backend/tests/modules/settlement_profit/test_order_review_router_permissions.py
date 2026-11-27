"""订单审核接口的权限：看 / 录成本 / 初审 / 终审 / 重算分开授权。不需要数据库（服务层打桩）。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.settlement_profit.order_review import router as order_router
from app.modules.settlement_profit.order_review import service
from app.modules.settlement_profit.order_review.schemas import (
    CostEntryRead,
    CostEntryResult,
    LookupData,
    RecalcResultData,
    ReviewLineResult,
    ReviewResultData,
)

READ = "page:finance:order-review:view"
COST = "action:finance:order-review:cost-entry"
REVIEW1 = "action:finance:order-review:review1"
REVIEW2 = "action:finance:order-review:review2"
RECALC = "action:finance:order-review:recalc"
BASE = "/api/finance/order-review"
ENTRY_ID = "00000000-0000-0000-0000-000000000001"
REVIEW_ID = "00000000-0000-0000-0000-000000000002"
COST_BODY = {
    "store_id": "990000000000000001",
    "scope": {"msku": "SYN-001", "shipping_list_code": "SP2026T0001"},
    "entry_kind": "confirm",
    "purchase_cny": "3.0000",
    "head_cny": "3.5000",
}
REVIEW_BODY = {"review_ids": [REVIEW_ID], "stage": "first", "decision": "pass"}


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TestClient]]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    get_settings.cache_clear()

    def build(principal: Principal | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_optional_principal] = lambda: principal
        app.dependency_overrides[get_db_session] = lambda: MagicMock()
        client = TestClient(app, raise_server_exceptions=False)
        # 写接口必须带 Idempotency-Key；单独的测试验证缺失时 422
        client.headers.update({"Idempotency-Key": "synthetic-key"})
        return client

    yield build
    get_settings.cache_clear()


CALLS: list[tuple[str, Any]] = []


def _entry() -> CostEntryRead:
    return CostEntryRead(
        id=UUID(ENTRY_ID),
        store_id="990000000000000001",
        msku="SYN-001",
        scope_ref="shipping:SP2026T0001",
        shipping_list_code="SP2026T0001",
        outbound_order_no=None,
        entry_kind="confirm",
        purchase_cny="3.0000",
        head_cny="3.5000",
        last_leg_cny=None,
        reason=None,
        status="pending_first",
        version=1,
        actor_id="u1",
        created_at=datetime(2026, 11, 27, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    CALLS.clear()
    monkeypatch.setattr(service, "list_periods", lambda session, **kw: [])
    monkeypatch.setattr(service, "list_lines", lambda session, **kw: ([], 0))
    monkeypatch.setattr(
        service, "lookup", lambda session, **kw: LookupData(kind="msku", items=[], truncated=False)
    )
    monkeypatch.setattr(service, "transaction_types", lambda session: [])

    def create(session, payload, **kw):
        CALLS.append(("cost", kw["actor_role"]))
        return CostEntryResult(entry=_entry(), affected_lines=1, recalculated_periods=1)

    def revoke(session, entry_id, payload, **kw):
        raise service.OrderReviewError(409, service.ERR_ALREADY_REVOKED, "已撤销")

    def review(session, payload, **kw):
        CALLS.append(("review", kw["actor_role"]))
        return ReviewResultData(
            items=[
                ReviewLineResult(
                    review_id=UUID(REVIEW_ID), line_key="k", ok=True, review_status="x", version=2
                )
            ],
            succeeded=1,
            failed=0,
        )

    monkeypatch.setattr(service, "get_cost_entry", lambda session, entry_id: _entry())
    monkeypatch.setattr(service, "create_cost_entry", create)
    monkeypatch.setattr(service, "revoke_cost_entry", revoke)
    monkeypatch.setattr(service, "review_lines", review)
    monkeypatch.setattr(
        service, "recalc", lambda session, payload: RecalcResultData(items=[], periods_total=0)
    )


def user(*permissions: str) -> Principal:
    return Principal(user_id="u1", permissions=frozenset(permissions))


ENDPOINTS = [
    ("GET", f"{BASE}/periods", None),
    ("GET", f"{BASE}/lines", None),
    ("GET", f"{BASE}/lookup?kind=msku", None),
    ("GET", f"{BASE}/transaction-types", None),
    ("GET", f"{BASE}/cost-entries/{ENTRY_ID}", None),
    ("POST", f"{BASE}/cost-entries", COST_BODY),
    ("POST", f"{BASE}/cost-entries/{ENTRY_ID}/revoke", {"reason": "x", "expected_version": 1}),
    ("POST", f"{BASE}/review", REVIEW_BODY),
    ("POST", f"{BASE}/recalc", {}),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_anonymous_gets_401(client_for, method: str, path: str, body) -> None:
    assert client_for(None).request(method, path, json=body).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_other_finance_users_get_403(client_for, method: str, path: str, body) -> None:
    other = user("page:finance:settlement-reconciliation:view")
    assert client_for(other).request(method, path, json=body).status_code == 403


def test_page_permission_reads_but_cannot_write(client_for) -> None:
    client = client_for(user(READ))
    assert client.get(f"{BASE}/periods").status_code == 200
    assert client.get(f"{BASE}/lines?page=1&page_size=50").status_code == 200
    assert client.get(f"{BASE}/transaction-types").status_code == 200
    assert client.get(f"{BASE}/cost-entries/{ENTRY_ID}").json()["data"]["version"] == 1
    assert client.post(f"{BASE}/cost-entries", json=COST_BODY).status_code == 403
    assert client.post(f"{BASE}/review", json=REVIEW_BODY).status_code == 403
    assert client.post(f"{BASE}/recalc", json={}).status_code == 403


def test_cost_entry_permission_and_idempotency_header(client_for) -> None:
    client = client_for(user(READ, COST))
    created = client.post(
        f"{BASE}/cost-entries", json=COST_BODY, headers={"Idempotency-Key": "idem-1"}
    )
    assert created.status_code == 201
    assert created.json()["data"]["entry"]["scope_ref"] == "shipping:SP2026T0001"
    assert CALLS == [("cost", COST)]
    revoked = client.post(
        f"{BASE}/cost-entries/{ENTRY_ID}/revoke", json={"reason": "x", "expected_version": 1}
    )
    assert (revoked.status_code, revoked.json()["error"]["code"]) == (409, "ALREADY_REVOKED")


def test_review1_cannot_do_final_review(client_for) -> None:
    client = client_for(user(READ, REVIEW1))
    first = client.post(f"{BASE}/review", json=REVIEW_BODY)
    assert (first.status_code, first.json()["data"]["succeeded"]) == (200, 1)
    assert CALLS == [("review", REVIEW1)]
    final = client.post(f"{BASE}/review", json={**REVIEW_BODY, "stage": "final"})
    assert final.status_code == 403
    assert client.post(f"{BASE}/recalc", json={}).status_code == 403


def test_review2_and_recalc(client_for) -> None:
    client = client_for(user(READ, REVIEW2, RECALC))
    assert client.post(f"{BASE}/review", json={**REVIEW_BODY, "stage": "final"}).status_code == 200
    assert client.post(f"{BASE}/review", json=REVIEW_BODY).status_code == 403
    assert client.post(f"{BASE}/recalc", json={"store_ids": []}).status_code == 200


def test_validation_errors_are_422(client_for) -> None:
    client = client_for(user(READ, COST))
    # 范围三选一在结构层校验（#373 P1 加了平台订单号范围）；修正原因仍在服务层（这里已打桩）
    no_scope = {**COST_BODY, "scope": {"msku": "SYN-001"}}
    assert client.post(f"{BASE}/cost-entries", json=no_scope).status_code == 422
    two_scopes = {
        **COST_BODY,
        "scope": {"msku": "SYN-001", "shipping_list_code": "SP2026T0001", "platform_order_no": "9"},
    }
    assert client.post(f"{BASE}/cost-entries", json=two_scopes).status_code == 422
    no_reason = {**COST_BODY, "entry_kind": "override"}
    assert client.post(f"{BASE}/cost-entries", json=no_reason).status_code == 201
    assert client.get(f"{BASE}/lines?page_size=500").status_code == 422
    assert client.post(f"{BASE}/review", json={**REVIEW_BODY, "review_ids": []}).status_code == 422


def test_router_module_has_no_db_access_without_dependency() -> None:
    assert order_router.router.prefix == BASE


def test_write_endpoints_require_idempotency_key(client_for) -> None:
    client = client_for(user(READ, COST, REVIEW1))
    del client.headers["Idempotency-Key"]
    assert client.post(f"{BASE}/cost-entries", json=COST_BODY).status_code == 422
    assert client.post(f"{BASE}/review", json=REVIEW_BODY).status_code == 422
    revoke = {"reason": "x", "expected_version": 1}
    entry = "00000000-0000-0000-0000-000000000001"
    assert client.post(f"{BASE}/cost-entries/{entry}/revoke", json=revoke).status_code == 422
