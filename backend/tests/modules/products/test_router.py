from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.products.dependencies import get_product_scope_provider
from app.modules.products.schemas import (
    Platform,
    ProductListData,
    ProductListingListData,
    ProductListingRead,
    ProductRead,
)
from app.modules.products.service import PRODUCT_SKU_CONFLICT, ProductService

PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000001")
LISTING_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
ALL_PERMISSIONS = frozenset(
    {
        "products:read",
        "products:create",
        "products:update",
        "product_listings:read",
        "product_listings:create",
        "product_listings:update",
    }
)


def _product_read() -> ProductRead:
    return ProductRead(
        id=PRODUCT_ID,
        sku="SKU-SYNTHETIC",
        product_name="Synthetic Product",
        category=None,
        product_type=None,
        status=None,
        grade=None,
        purchase_price=Decimal("12.3400"),
        currency_code="USD",
        declared_cn_name=None,
        declared_en_name=None,
        material_cn=None,
        material_en=None,
        remark=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _listing_read() -> ProductListingRead:
    return ProductListingRead(
        id=LISTING_ID,
        product_id=PRODUCT_ID,
        platform=Platform.WALMART,
        store_name="Synthetic Store",
        msku="MSKU-SYNTHETIC",
        external_listing_id=None,
        listing_url=None,
        listing_status=None,
        fulfillment_type=None,
        wfs_fee=None,
        shipping_cost=None,
        currency_code=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _allowed_app(*permissions: str) -> FastAPI:
    application = create_app()
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions) if permissions else ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_optional_principal] = lambda: principal
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _assert_envelope(response: Any, expected_status: int) -> dict[str, Any]:
    assert response.status_code == expected_status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def test_all_routes_fail_closed_without_principal_or_scope() -> None:
    unauthorized = TestClient(create_app()).get("/api/v1/products/options")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == ErrorCode.UNAUTHORIZED

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=ALL_PERMISSIONS,
    )
    denied = TestClient(application).get("/api/v1/products/options")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == ErrorCode.DATA_SCOPE_DENIED


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("GET", "/api/v1/products", None),
        ("GET", f"/api/v1/products/{PRODUCT_ID}", None),
        ("POST", "/api/v1/products", {"sku": "SKU", "product_name": "Synthetic"}),
        ("PATCH", f"/api/v1/products/{PRODUCT_ID}", {"product_name": "Synthetic"}),
        ("GET", "/api/v1/products/options", None),
        ("GET", f"/api/v1/products/{PRODUCT_ID}/listings", None),
        (
            "POST",
            f"/api/v1/products/{PRODUCT_ID}/listings",
            {"platform": "walmart", "store_name": "Store", "msku": "MSKU"},
        ),
        (
            "PATCH",
            f"/api/v1/products/{PRODUCT_ID}/listings/{LISTING_ID}",
            {"listing_status": "active"},
        ),
    ],
)
def test_each_route_requires_its_permission(method: str, path: str, json: object) -> None:
    application = _allowed_app("unrelated:permission")
    response = TestClient(application).request(method, path, json=json)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN


def test_eight_routes_return_shared_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _product_read()
    listing = _listing_read()
    monkeypatch.setattr(
        ProductService,
        "list_products",
        lambda self, query: ProductListData(
            items=[product], total=1, page=query.page, page_size=query.page_size
        ),
    )
    monkeypatch.setattr(ProductService, "get_product", lambda self, product_id: product)
    monkeypatch.setattr(ProductService, "create_product", lambda self, payload: product)
    monkeypatch.setattr(
        ProductService,
        "update_product",
        lambda self, product_id, payload: product,
    )
    monkeypatch.setattr(
        ProductService,
        "list_listings",
        lambda self, product_id, query: ProductListingListData(
            items=[listing], total=1, page=query.page, page_size=query.page_size
        ),
    )
    monkeypatch.setattr(ProductService, "create_listing", lambda self, product_id, payload: listing)
    monkeypatch.setattr(
        ProductService,
        "update_listing",
        lambda self, product_id, listing_id, payload: listing,
    )

    client = TestClient(_allowed_app())
    responses = [
        client.get("/api/v1/products"),
        client.get(f"/api/v1/products/{PRODUCT_ID}"),
        client.post(
            "/api/v1/products",
            json={"sku": "SKU-SYNTHETIC", "product_name": "Synthetic Product"},
        ),
        client.patch(
            f"/api/v1/products/{PRODUCT_ID}",
            json={"product_name": "Updated Synthetic Product"},
        ),
        client.get("/api/v1/products/options"),
        client.get(f"/api/v1/products/{PRODUCT_ID}/listings"),
        client.post(
            f"/api/v1/products/{PRODUCT_ID}/listings",
            json={
                "platform": "walmart",
                "store_name": "Synthetic Store",
                "msku": "MSKU-SYNTHETIC",
            },
        ),
        client.patch(
            f"/api/v1/products/{PRODUCT_ID}/listings/{LISTING_ID}",
            json={"listing_status": "active"},
        ),
    ]

    for response, expected_status in zip(
        responses,
        (200, 200, 201, 200, 200, 200, 201, 200),
        strict=True,
    ):
        body = _assert_envelope(response, expected_status)
        assert body["success"] is True
        assert body["error"] is None

    assert responses[0].json()["data"]["items"][0]["purchase_price"] == "12.3400"
    assert responses[4].json()["data"] == {"platforms": ["walmart", "amazon", "temu", "other"]}


def test_transport_validation_and_conflict_errors_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_allowed_app())

    unknown_query = client.get("/api/v1/products", params={"unknown": "private-value"})
    assert unknown_query.status_code == 422
    assert "private-value" not in unknown_query.text

    invalid_money = client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-SYNTHETIC",
            "product_name": "Synthetic",
            "purchase_price": 1.25,
            "currency_code": "USD",
        },
    )
    assert invalid_money.status_code == 422
    assert "1.25" not in invalid_money.text

    def conflict(self: ProductService, payload: object) -> None:
        raise ApiError(code=PRODUCT_SKU_CONFLICT, status_code=409)

    monkeypatch.setattr(ProductService, "create_product", conflict)
    response = client.post(
        "/api/v1/products",
        json={"sku": "SKU-SYNTHETIC", "product_name": "Synthetic"},
    )
    body = _assert_envelope(response, 409)
    assert body["error"]["code"] == PRODUCT_SKU_CONFLICT
    assert "SKU-SYNTHETIC" not in response.text


def test_openapi_contains_only_approved_product_routes_and_models() -> None:
    schema = create_app().openapi()
    product_paths = {path for path in schema["paths"] if path.startswith("/api/v1/products")}

    assert product_paths == {
        "/api/v1/products",
        "/api/v1/products/options",
        "/api/v1/products/{product_id}",
        "/api/v1/products/{product_id}/listings",
        "/api/v1/products/{product_id}/listings/{listing_id}",
    }
    assert set(schema["paths"]["/api/v1/products"]) == {"get", "post"}
    assert set(schema["paths"]["/api/v1/products/{product_id}"]) == {"get", "patch"}
    assert set(schema["paths"]["/api/v1/products/{product_id}/listings"]) == {
        "get",
        "post",
    }
    assert set(schema["paths"]["/api/v1/products/{product_id}/listings/{listing_id}"]) == {"patch"}
    assert "ProductRead" in schema["components"]["schemas"]
    assert "ProductListingRead" in schema["components"]["schemas"]
    assert schema["paths"]["/api/v1/products"]["get"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_health_remains_database_independent() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}
