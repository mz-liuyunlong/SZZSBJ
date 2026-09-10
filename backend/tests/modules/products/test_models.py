from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import DateTime, Numeric, String, Table

from app.db.base import Base
from app.modules.products.models import Product, ProductPlatformListing
from app.modules.products.schemas import (
    Platform,
    ProductCreate,
    ProductListingCreate,
    ProductListingRead,
    ProductListingUpdate,
    ProductUpdate,
)


def test_models_match_approved_grains_and_constraints() -> None:
    assert set(Base.metadata.tables) >= {"products", "product_platform_listings"}

    products = cast(Table, Product.__table__)
    assert cast(String, products.c.sku.type).length == 128
    assert products.c.sku.nullable is False
    assert products.c.product_name.nullable is False
    assert isinstance(products.c.purchase_price.type, Numeric)
    purchase_price_type = products.c.purchase_price.type
    assert (purchase_price_type.precision, purchase_price_type.scale) == (18, 4)
    assert isinstance(products.c.created_at.type, DateTime)
    assert products.c.created_at.type.timezone is True
    assert products.c.deleted_at.nullable is True
    assert {constraint.name for constraint in products.constraints} >= {
        "pk_products",
        "uq_products_sku",
        "ck_products_purchase_price_currency_pair",
        "ck_products_purchase_price_nonnegative",
    }

    listings = cast(Table, ProductPlatformListing.__table__)
    assert next(iter(listings.c.product_id.foreign_keys)).target_fullname == "products.id"
    assert isinstance(listings.c.wfs_fee.type, Numeric)
    assert isinstance(listings.c.shipping_cost.type, Numeric)
    wfs_fee_type = listings.c.wfs_fee.type
    assert (wfs_fee_type.precision, wfs_fee_type.scale) == (18, 4)
    assert listings.c.deleted_at.nullable is True
    assert {constraint.name for constraint in listings.constraints} >= {
        "pk_product_platform_listings",
        "uq_product_platform_listings_platform",
        "ck_product_platform_listings_platform_allowed",
        "ck_product_platform_listings_money_currency_required",
    }
    assert {index.name for index in listings.indexes} == {"ix_product_platform_listings_product_id"}


def test_product_schema_trims_identity_and_serializes_decimal_as_string() -> None:
    payload = ProductCreate(
        sku="  SKU-SYNTHETIC  ",
        product_name="  Synthetic Product  ",
        purchase_price=Decimal("12.3400"),
        currency_code="USD",
    )

    assert payload.sku == "SKU-SYNTHETIC"
    assert payload.product_name == "Synthetic Product"
    assert payload.purchase_price == Decimal("12.3400")
    assert payload.model_dump(mode="json")["purchase_price"] == "12.3400"


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"sku": " ", "product_name": "Synthetic"}, "string_too_short"),
        (
            {"sku": "SKU", "product_name": "Synthetic", "purchase_price": 1.25},
            "value_error",
        ),
        (
            {"sku": "SKU", "product_name": "Synthetic", "purchase_price": "1.00001"},
            "decimal_max_places",
        ),
        (
            {"sku": "SKU", "product_name": "Synthetic", "purchase_price": "1.0000"},
            "value_error",
        ),
        (
            {
                "sku": "SKU",
                "product_name": "Synthetic",
                "purchase_price": "1.0000",
                "currency_code": "usd",
            },
            "string_pattern_mismatch",
        ),
        ({"sku": "SKU", "product_name": "Synthetic", "unknown": "value"}, "extra_forbidden"),
    ],
)
def test_product_schema_rejects_invalid_contract_values(
    values: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        ProductCreate.model_validate(values)

    assert reason in {item["type"] for item in error.value.errors()}


def test_patch_requires_a_field_and_preserves_nullable_clear_semantics() -> None:
    with pytest.raises(ValidationError):
        ProductUpdate()
    with pytest.raises(ValidationError):
        ProductUpdate(sku=None)

    patch = ProductUpdate(purchase_price=None, currency_code=None)
    assert patch.model_dump(exclude_unset=True) == {
        "purchase_price": None,
        "currency_code": None,
    }


def test_listing_schema_enforces_identity_platform_and_money_contract() -> None:
    payload = ProductListingCreate(
        platform=Platform.WALMART,
        store_name="  Synthetic Store  ",
        msku="  MSKU-SYNTHETIC  ",
        wfs_fee=Decimal("2.5000"),
        currency_code="USD",
    )
    assert payload.store_name == "Synthetic Store"
    assert payload.msku == "MSKU-SYNTHETIC"

    for invalid in (
        {"platform": "unknown", "store_name": "Store", "msku": "MSKU"},
        {"platform": "walmart", "store_name": " ", "msku": "MSKU"},
        {
            "platform": "walmart",
            "store_name": "Store",
            "msku": "MSKU",
            "shipping_cost": "1.0000",
        },
    ):
        with pytest.raises(ValidationError):
            ProductListingCreate.model_validate(invalid)

    with pytest.raises(ValidationError):
        ProductListingUpdate()
    with pytest.raises(ValidationError):
        ProductListingUpdate(platform=None)


def test_listing_read_omits_deleted_at_and_serializes_money() -> None:
    data = ProductListingRead(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        product_id=UUID("00000000-0000-0000-0000-000000000001"),
        platform=Platform.OTHER,
        store_name="Synthetic Store",
        msku="MSKU-SYNTHETIC",
        external_listing_id=None,
        listing_url=None,
        listing_status=None,
        fulfillment_type=None,
        wfs_fee=Decimal("1.0000"),
        shipping_cost=None,
        currency_code="USD",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    body = data.model_dump(mode="json")
    assert body["wfs_fee"] == "1.0000"
    assert "deleted_at" not in body
