from datetime import UTC, datetime
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
    ListingManagementItemRead,
    ListingManagementListData,
)
from app.modules.data_pages.service import ListingManagementService
from app.modules.integration_sync.dependencies import get_source_account_scope_provider

ALL_PERMISSIONS = frozenset({"products:read"})
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


def _listing_item() -> ListingManagementItemRead:
    return ListingManagementItemRead(
        id="00000000-0000-0000-0000-000000000003",
        source_account_ref="synthetic-account",
        platform_code="10008",
        store_id="store-1",
        store_name="Walmart US",
        item_id="item-1",
        msku="msku-1",
        local_sku="sku-1",
        local_name="Synthetic Listing",
        title="Synthetic Listing Title",
        picture_url="https://example.invalid/listing.jpg",
        item_url="https://example.invalid/item-1",
        owner_ref="owner-1",
        product_grade="A级",
        tags=["主推"],
        strike_price_amount=Decimal("49.99"),
        strike_price_currency_code="USD",
        sale_price_amount=Decimal("39.99"),
        sale_price_currency_code="USD",
        listing_status="在线",
        lifecycle_status="成长期",
        listing_start_at_utc=NOW,
        category="家居",
        wfs_available_quantity=Decimal("12"),
        available_quantity=Decimal("2"),
        inbound_quantity=Decimal("4"),
        sales_7d=Decimal("3"),
        sales_14d=Decimal("7"),
        sales_30d=Decimal("15"),
        ad_spend_30d_amount=Decimal("21.50"),
        ad_spend_currency_code="USD",
        buybox_status="拥有",
        walmart_seller="Walmart",
        is_hijacked=False,
        average_rating=Decimal("4.500000"),
        review_count=18,
        brand="SyntheticBrand",
        disabled_reason=None,
        wfs_fee_amount=Decimal("3.50"),
        wfs_fee_currency_code="USD",
        gtin="0085000100001",
        upc="85000100001",
        calculated_at=NOW,
    )


def test_openapi_contains_listing_management_route() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/listings/walmart" in paths


def test_listing_management_route_fails_closed_for_auth_permission_and_scope() -> None:
    assert TestClient(create_app()).get("/api/listings/walmart").status_code == 401

    denied = TestClient(_app("unrelated:permission")).get("/api/listings/walmart")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).get("/api/listings/walmart")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_listing_management_route_returns_envelope_and_meta(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def list_listings(
        self: ListingManagementService,
        query: Any,
        account_refs: frozenset[str],
    ) -> tuple[ListingManagementListData, int, datetime]:
        captured["query"] = query
        captured["account_refs"] = account_refs
        return ListingManagementListData(items=[_listing_item()]), 1, NOW

    monkeypatch.setattr(ListingManagementService, "list_listings", list_listings)

    response = TestClient(_app()).get(
        "/api/listings/walmart",
        params={
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
    assert body["data"]["items"][0]["sale_price_amount"] == "39.99"
    assert body["meta"]["source_objects"] == ["mart_listing_management_current"]
    assert body["meta"]["total"] == 1
