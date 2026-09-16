from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.schemas import OrderProfitItemRead, OrderProfitListData
from app.modules.data_pages.service import OrderProfitService
from app.modules.integration_sync.dependencies import get_source_account_scope_provider

ALL_PERMISSIONS = frozenset({"sales:daily-sales:read"})
NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


def _app(*permissions: str) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions) if permissions else ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({"synthetic-account"})
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _assert_envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def _order_profit_item() -> OrderProfitItemRead:
    return OrderProfitItemRead(
        id="00000000-0000-0000-0000-000000000101",
        business_date_la=date(2026, 9, 16),
        business_timezone="America/Los_Angeles",
        local_sku="sku-1",
        item_ids=["item-1"],
        store_ids=["store-1"],
        store_count=1,
        item_count=1,
        sales_qty=Decimal("3"),
        order_count=Decimal("2"),
        sales_amount=Decimal("39.99"),
        sales_currency_code="USD",
        refund_amount=Decimal("0"),
        ad_spend_amount=Decimal("5.25"),
        commission_fee_amount=Decimal("6.00"),
        wfs_fee_total_amount=Decimal("10.50"),
        purchase_cost_total_usd=Decimal("4.00"),
        first_leg_cost_total_usd=Decimal("0.55"),
        storage_fee_total_amount=Decimal("0.06"),
        gross_profit_amount=Decimal("13.63"),
        gross_profit_currency_code="USD",
        gross_margin=Decimal("0.340000"),
        roi=Decimal("2.590000"),
        cost_status="complete",
        missing_cost_codes=[],
        calc_version="synthetic-v1",
        calculated_at=NOW,
    )


def test_openapi_contains_order_profit_route() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/sales/order-profit" in paths


def test_order_profit_route_fails_closed_for_auth_permission_and_scope() -> None:
    assert TestClient(create_app()).get("/api/sales/order-profit").status_code == 401

    denied = TestClient(_app("unrelated:permission")).get("/api/sales/order-profit")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).get("/api/sales/order-profit")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_order_profit_route_returns_envelope_and_meta(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def list_order_profit(
        self: OrderProfitService,
        query: Any,
        account_refs: frozenset[str],
    ) -> tuple[OrderProfitListData, int, datetime]:
        captured["query"] = query
        captured["account_refs"] = account_refs
        return OrderProfitListData(items=[_order_profit_item()]), 1, NOW

    monkeypatch.setattr(OrderProfitService, "list_order_profit", list_order_profit)

    response = TestClient(_app()).get(
        "/api/sales/order-profit",
        params={
            "start_date": "2026-09-16",
            "end_date": "2026-09-16",
            "search_field": "sku",
            "keyword": "sku-1",
            "page": 2,
            "page_size": 50,
        },
    )

    body = _assert_envelope(response)
    assert captured["account_refs"] == frozenset({"synthetic-account"})
    assert captured["query"].page == 2
    assert captured["query"].page_size == 50
    assert body["data"]["items"][0]["local_sku"] == "sku-1"
    assert body["data"]["items"][0]["sales_amount"] == "39.99"
    assert body["meta"]["source_objects"] == ["mart_order_profit_sku_day"]
    assert body["meta"]["total"] == 1
