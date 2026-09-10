from typing import Never
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.products.models import Product, ProductPlatformListing
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import (
    Platform,
    ProductCreate,
    ProductListData,
    ProductListingCreate,
    ProductListingListData,
    ProductListingListQuery,
    ProductListingRead,
    ProductListingUpdate,
    ProductListQuery,
    ProductOptionsData,
    ProductRead,
    ProductUpdate,
)

PRODUCT_SKU_CONFLICT = "PRODUCT_SKU_CONFLICT"
LISTING_IDENTITY_CONFLICT = "LISTING_IDENTITY_CONFLICT"


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProductRepository(session)

    def list_products(self, query: ProductListQuery) -> ProductListData:
        products, total = self.repository.list_products(
            page=query.page,
            page_size=query.page_size,
            sku=query.sku,
            product_name=query.product_name,
            platform=query.platform.value if query.platform is not None else None,
            store_name=query.store_name,
            msku=query.msku,
        )
        return ProductListData(
            items=[ProductRead.model_validate(product) for product in products],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def get_product(self, product_id: UUID) -> ProductRead:
        return ProductRead.model_validate(self._require_product(product_id))

    def create_product(self, payload: ProductCreate) -> ProductRead:
        if self.repository.find_product_by_sku(payload.sku) is not None:
            self._conflict(PRODUCT_SKU_CONFLICT)
        product = Product(**payload.model_dump())
        try:
            self.repository.add_product(product)
            self.session.commit()
        except IntegrityError:
            self._conflict(PRODUCT_SKU_CONFLICT)
        return ProductRead.model_validate(product)

    def update_product(self, product_id: UUID, payload: ProductUpdate) -> ProductRead:
        product = self._require_product(product_id)
        values = payload.model_dump(exclude_unset=True)
        sku = values.get("sku")
        if (
            isinstance(sku, str)
            and self.repository.find_product_by_sku(
                sku,
                exclude_id=product_id,
            )
            is not None
        ):
            self._conflict(PRODUCT_SKU_CONFLICT)
        self._validate_product_money(
            values.get("purchase_price", product.purchase_price),
            values.get("currency_code", product.currency_code),
        )
        try:
            self.repository.update_product(product, values)
            self.session.commit()
        except IntegrityError:
            self._conflict(PRODUCT_SKU_CONFLICT)
        return ProductRead.model_validate(product)

    @staticmethod
    def options() -> ProductOptionsData:
        return ProductOptionsData(platforms=list(Platform))

    def list_listings(
        self,
        product_id: UUID,
        query: ProductListingListQuery,
    ) -> ProductListingListData:
        self._require_product(product_id)
        listings, total = self.repository.list_listings(
            product_id=product_id,
            page=query.page,
            page_size=query.page_size,
        )
        return ProductListingListData(
            items=[ProductListingRead.model_validate(listing) for listing in listings],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def create_listing(
        self,
        product_id: UUID,
        payload: ProductListingCreate,
    ) -> ProductListingRead:
        self._require_product(product_id)
        if (
            self.repository.find_listing_by_identity(
                platform=payload.platform.value,
                store_name=payload.store_name,
                msku=payload.msku,
            )
            is not None
        ):
            self._conflict(LISTING_IDENTITY_CONFLICT)
        listing = ProductPlatformListing(product_id=product_id, **payload.model_dump())
        try:
            self.repository.add_listing(listing)
            self.session.commit()
        except IntegrityError:
            self._conflict(LISTING_IDENTITY_CONFLICT)
        return ProductListingRead.model_validate(listing)

    def update_listing(
        self,
        product_id: UUID,
        listing_id: UUID,
        payload: ProductListingUpdate,
    ) -> ProductListingRead:
        self._require_product(product_id)
        listing = self.repository.get_listing(product_id, listing_id)
        if listing is None:
            self._not_found()
        values = payload.model_dump(exclude_unset=True)
        platform = values.get("platform", listing.platform)
        store_name = values.get("store_name", listing.store_name)
        msku = values.get("msku", listing.msku)
        platform_value = platform.value if isinstance(platform, Platform) else platform
        if (
            self.repository.find_listing_by_identity(
                platform=str(platform_value),
                store_name=str(store_name),
                msku=str(msku),
                exclude_id=listing_id,
            )
            is not None
        ):
            self._conflict(LISTING_IDENTITY_CONFLICT)
        self._validate_listing_money(
            values.get("wfs_fee", listing.wfs_fee),
            values.get("shipping_cost", listing.shipping_cost),
            values.get("currency_code", listing.currency_code),
        )
        try:
            self.repository.update_listing(listing, values)
            self.session.commit()
        except IntegrityError:
            self._conflict(LISTING_IDENTITY_CONFLICT)
        return ProductListingRead.model_validate(listing)

    def _require_product(self, product_id: UUID) -> Product:
        product = self.repository.get_product(product_id)
        if product is None:
            self._not_found()
        return product

    @staticmethod
    def _validate_product_money(
        purchase_price: object,
        currency_code: object,
    ) -> None:
        if (purchase_price is None) != (currency_code is None):
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    @staticmethod
    def _validate_listing_money(
        wfs_fee: object,
        shipping_cost: object,
        currency_code: object,
    ) -> None:
        if (wfs_fee is not None or shipping_cost is not None) and currency_code is None:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    @staticmethod
    def _not_found() -> Never:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    @staticmethod
    def _conflict(code: str) -> Never:
        raise ApiError(code=code, status_code=409)
