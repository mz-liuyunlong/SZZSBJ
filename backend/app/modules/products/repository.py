from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.products.models import Product, ProductPlatformListing


class ProductRepository:
    """Product persistence boundary; callers own transactions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(
        self,
        *,
        page: int,
        page_size: int,
        sku: str | None,
        product_name: str | None,
        platform: str | None,
        store_name: str | None,
        msku: str | None,
    ) -> tuple[list[Product], int]:
        conditions: list[ColumnElement[bool]] = [Product.deleted_at.is_(None)]
        if sku is not None:
            conditions.append(Product.sku.contains(sku, autoescape=True))
        if product_name is not None:
            conditions.append(Product.product_name.contains(product_name, autoescape=True))

        listing_conditions: list[ColumnElement[bool]] = [
            ProductPlatformListing.product_id == Product.id,
            ProductPlatformListing.deleted_at.is_(None),
        ]
        if platform is not None:
            listing_conditions.append(ProductPlatformListing.platform == platform)
        if store_name is not None:
            listing_conditions.append(ProductPlatformListing.store_name == store_name)
        if msku is not None:
            listing_conditions.append(ProductPlatformListing.msku == msku)
        if any(value is not None for value in (platform, store_name, msku)):
            conditions.append(exists(select(1).where(and_(*listing_conditions))))

        total = self.session.scalar(select(func.count()).select_from(Product).where(*conditions))
        statement = (
            select(Product)
            .where(*conditions)
            .order_by(Product.sku.asc(), Product.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(statement).all()), int(total or 0)

    def get_product(self, product_id: UUID) -> Product | None:
        return self.session.scalar(
            select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
        )

    def find_product_by_sku(
        self,
        sku: str,
        *,
        exclude_id: UUID | None = None,
    ) -> Product | None:
        statement = select(Product).where(Product.sku == sku)
        if exclude_id is not None:
            statement = statement.where(Product.id != exclude_id)
        return self.session.scalar(statement.limit(1))

    def add_product(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        return product

    def update_product(self, product: Product, values: Mapping[str, object]) -> Product:
        for name, value in values.items():
            setattr(product, name, value)
        self.session.flush()
        return product

    def list_listings(
        self,
        *,
        product_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ProductPlatformListing], int]:
        conditions: list[ColumnElement[bool]] = [
            ProductPlatformListing.product_id == product_id,
            ProductPlatformListing.deleted_at.is_(None),
        ]
        total = self.session.scalar(
            select(func.count()).select_from(ProductPlatformListing).where(*conditions)
        )
        statement = (
            select(ProductPlatformListing)
            .where(*conditions)
            .order_by(
                ProductPlatformListing.platform.asc(),
                ProductPlatformListing.store_name.asc(),
                ProductPlatformListing.msku.asc(),
                ProductPlatformListing.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(statement).all()), int(total or 0)

    def get_listing(
        self,
        product_id: UUID,
        listing_id: UUID,
    ) -> ProductPlatformListing | None:
        return self.session.scalar(
            select(ProductPlatformListing).where(
                ProductPlatformListing.id == listing_id,
                ProductPlatformListing.product_id == product_id,
                ProductPlatformListing.deleted_at.is_(None),
            )
        )

    def find_listing_by_identity(
        self,
        *,
        platform: str,
        store_name: str,
        msku: str,
        exclude_id: UUID | None = None,
    ) -> ProductPlatformListing | None:
        statement = select(ProductPlatformListing).where(
            ProductPlatformListing.platform == platform,
            ProductPlatformListing.store_name == store_name,
            ProductPlatformListing.msku == msku,
        )
        if exclude_id is not None:
            statement = statement.where(ProductPlatformListing.id != exclude_id)
        return self.session.scalar(statement.limit(1))

    def add_listing(self, listing: ProductPlatformListing) -> ProductPlatformListing:
        self.session.add(listing)
        self.session.flush()
        return listing

    def update_listing(
        self,
        listing: ProductPlatformListing,
        values: Mapping[str, object],
    ) -> ProductPlatformListing:
        for name, value in values.items():
            setattr(listing, name, value)
        self.session.flush()
        return listing
