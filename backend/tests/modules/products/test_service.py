from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.products.models import Product, ProductPlatformListing
from app.modules.products.schemas import (
    Platform,
    ProductCreate,
    ProductListingCreate,
    ProductListingUpdate,
    ProductUpdate,
)
from app.modules.products.service import (
    LISTING_IDENTITY_CONFLICT,
    PRODUCT_SKU_CONFLICT,
    ProductService,
)

PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000001")
LISTING_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _product() -> Product:
    return Product(
        id=PRODUCT_ID,
        sku="SKU-SYNTHETIC",
        product_name="Synthetic Product",
        created_at=NOW,
        updated_at=NOW,
    )


def _listing() -> ProductPlatformListing:
    return ProductPlatformListing(
        id=LISTING_ID,
        product_id=PRODUCT_ID,
        platform=Platform.WALMART,
        store_name="Synthetic Store",
        msku="MSKU-SYNTHETIC",
        created_at=NOW,
        updated_at=NOW,
    )


def test_create_product_commits_once_and_maps_to_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    monkeypatch.setattr(service.repository, "find_product_by_sku", MagicMock(return_value=None))

    def add(product: Product) -> Product:
        product.id = PRODUCT_ID
        product.created_at = NOW
        product.updated_at = NOW
        return product

    monkeypatch.setattr(service.repository, "add_product", MagicMock(side_effect=add))

    result = service.create_product(
        ProductCreate(sku="SKU-SYNTHETIC", product_name="Synthetic Product")
    )

    assert result.id == PRODUCT_ID
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_product_conflicts_are_safe_and_do_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    monkeypatch.setattr(
        service.repository,
        "find_product_by_sku",
        MagicMock(return_value=_product()),
    )

    with pytest.raises(ApiError) as conflict:
        service.create_product(ProductCreate(sku="SKU-SYNTHETIC", product_name="Synthetic"))

    assert conflict.value.code == PRODUCT_SKU_CONFLICT
    assert conflict.value.status_code == 409
    assert conflict.value.details == {}
    session.commit.assert_not_called()


def test_integrity_error_is_mapped_without_database_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    monkeypatch.setattr(service.repository, "find_product_by_sku", MagicMock(return_value=None))
    monkeypatch.setattr(
        service.repository,
        "add_product",
        MagicMock(side_effect=IntegrityError("private statement", {}, Exception("private"))),
    )

    with pytest.raises(ApiError) as conflict:
        service.create_product(ProductCreate(sku="SKU-SYNTHETIC", product_name="Synthetic"))

    assert conflict.value.code == PRODUCT_SKU_CONFLICT
    assert "private" not in str(conflict.value)
    session.commit.assert_not_called()


def test_product_patch_validates_combined_money_state(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    product = _product()
    product.purchase_price = Decimal("1.0000")
    product.currency_code = "USD"
    monkeypatch.setattr(service.repository, "get_product", MagicMock(return_value=product))

    with pytest.raises(ApiError) as invalid:
        service.update_product(PRODUCT_ID, ProductUpdate(currency_code=None))

    assert invalid.value.code == ErrorCode.VALIDATION_ERROR
    assert invalid.value.status_code == 422
    session.commit.assert_not_called()


def test_listing_create_and_update_commit_through_service(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    product = _product()
    listing = _listing()
    monkeypatch.setattr(service.repository, "get_product", MagicMock(return_value=product))
    monkeypatch.setattr(
        service.repository,
        "find_listing_by_identity",
        MagicMock(return_value=None),
    )

    def add(created: ProductPlatformListing) -> ProductPlatformListing:
        created.id = LISTING_ID
        created.created_at = NOW
        created.updated_at = NOW
        return created

    monkeypatch.setattr(service.repository, "add_listing", MagicMock(side_effect=add))
    created = service.create_listing(
        PRODUCT_ID,
        ProductListingCreate(
            platform=Platform.WALMART,
            store_name="Synthetic Store",
            msku="MSKU-SYNTHETIC",
        ),
    )
    assert created.id == LISTING_ID

    monkeypatch.setattr(service.repository, "get_listing", MagicMock(return_value=listing))

    def update(
        current: ProductPlatformListing,
        values: dict[str, object],
    ) -> ProductPlatformListing:
        for name, value in values.items():
            setattr(current, name, value)
        return current

    monkeypatch.setattr(service.repository, "update_listing", MagicMock(side_effect=update))
    updated = service.update_listing(
        PRODUCT_ID,
        LISTING_ID,
        ProductListingUpdate(listing_status="active"),
    )
    assert updated.listing_status == "active"
    assert session.commit.call_count == 2


def test_listing_identity_conflict_and_not_found_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = ProductService(session)
    monkeypatch.setattr(service.repository, "get_product", MagicMock(return_value=_product()))
    monkeypatch.setattr(
        service.repository,
        "find_listing_by_identity",
        MagicMock(return_value=_listing()),
    )

    with pytest.raises(ApiError) as conflict:
        service.create_listing(
            PRODUCT_ID,
            ProductListingCreate(
                platform=Platform.WALMART,
                store_name="Synthetic Store",
                msku="MSKU-SYNTHETIC",
            ),
        )
    assert conflict.value.code == LISTING_IDENTITY_CONFLICT

    monkeypatch.setattr(service.repository, "get_product", MagicMock(return_value=None))
    with pytest.raises(ApiError) as missing:
        service.get_product(PRODUCT_ID)
    assert missing.value.code == ErrorCode.NOT_FOUND
