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
from app.modules.data_pages.schemas import (
    DailySalesItemRead,
    DailySalesListData,
    DailySalesSummaryRead,
    DailySalesTrendPointRead,
)
from app.modules.data_pages.service import DailySalesService
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


def _daily_sales_item() -> DailySalesItemRead:
    return DailySalesItemRead(
        id="00000000-0000-0000-0000-000000000001",
        business_date_la=date(2026, 9, 16),
        business_timezone="America/Los_Angeles",
        store_id="store-1",
        store_name="Walmart US",
        owner_ref="owner-1",
        item_id="item-1",
        msku="msku-1",
        local_sku="sku-1",
        local_name="Synthetic Product",
        title="Synthetic Title",
        picture_url="https://example.invalid/image.jpg",
        platform_code="10008",
        sales_qty=Decimal("3"),
        order_count=Decimal("2"),
        sales_amount=Decimal("39.99"),
        sales_currency_code="USD",
        sample_amount=Decimal("0"),
        sales_amount_excluding_sample=Decimal("39.99"),
        return_qty=Decimal("0"),
        refund_amount=Decimal("0"),
        refund_currency_code="USD",
        return_rate_30d=Decimal("0"),
        ad_spend_amount=Decimal("5.25"),
        ad_spend_currency_code="USD",
        ad_ratio=Decimal("0.131282"),
        wfs_available_quantity=Decimal("12"),
        wfs_fee_unit_amount=Decimal("3.50"),
        wfs_fee_total_amount=Decimal("10.50"),
        wfs_fee_currency_code="USD",
        purchase_cost_unit_cny=Decimal("8.80"),
        purchase_cost_total_usd=Decimal("4.00"),
        first_leg_cost_unit_cny=Decimal("1.20"),
        first_leg_cost_total_usd=Decimal("0.55"),
        storage_fee_unit_amount=Decimal("0.02"),
        storage_fee_total_amount=Decimal("0.06"),
        storage_fee_currency_code="USD",
        commission_rate=Decimal("0.15"),
        commission_fee_amount=Decimal("6.00"),
        commission_fee_currency_code="USD",
        gross_profit_amount=Decimal("13.63"),
        gross_profit_currency_code="USD",
        gross_margin=Decimal("0.340000"),
        roi=Decimal("2.590000"),
        cost_status="complete",
        missing_cost_codes=[],
        sales_7d_trend=[DailySalesTrendPointRead(date=date(2026, 9, 16), sales_qty=Decimal("3"))],
        calc_version="synthetic-v1",
        calculated_at=NOW,
    )


def test_openapi_contains_daily_sales_route() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/sales/daily-sales" in paths


def test_daily_sales_route_fails_closed_for_auth_permission_and_scope() -> None:
    assert TestClient(create_app()).get("/api/sales/daily-sales").status_code == 401

    denied = TestClient(_app("unrelated:permission")).get("/api/sales/daily-sales")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).get("/api/sales/daily-sales")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_daily_sales_route_returns_envelope_and_meta(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def list_daily_sales(
        self: DailySalesService,
        query: Any,
        account_refs: frozenset[str],
    ) -> tuple[DailySalesListData, int, datetime]:
        captured["query"] = query
        captured["account_refs"] = account_refs
        return (
            DailySalesListData(
                items=[_daily_sales_item()],
                summary=DailySalesSummaryRead(
                    refund_event_qty=Decimal("36"),
                    refund_event_amount=Decimal("674.80"),
                    refund_event_currency_code="USD",
                ),
            ),
            1,
            NOW,
        )

    monkeypatch.setattr(DailySalesService, "list_daily_sales", list_daily_sales)

    response = TestClient(_app()).get(
        "/api/sales/daily-sales",
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
    assert body["data"]["summary"]["refund_event_qty"] == "36.00"
    assert body["data"]["summary"]["refund_event_amount"] == "674.80"
    assert body["meta"]["source_objects"] == [
        "mart_daily_sales_item_day",
        "fact_walmart_refund_items",
    ]
    assert body["meta"]["total"] == 1
