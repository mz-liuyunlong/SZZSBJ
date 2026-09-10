from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku"),
        CheckConstraint(
            "(purchase_price IS NULL AND currency_code IS NULL) OR "
            "(purchase_price IS NOT NULL AND currency_code IS NOT NULL)",
            name="ck_products_purchase_price_currency_pair",
        ),
        CheckConstraint(
            "purchase_price IS NULL OR purchase_price >= 0",
            name="ck_products_purchase_price_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    product_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    grade: Mapped[str | None] = mapped_column(String(64))
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    declared_cn_name: Mapped[str | None] = mapped_column(String(255))
    declared_en_name: Mapped[str | None] = mapped_column(String(255))
    material_cn: Mapped[str | None] = mapped_column(String(255))
    material_en: Mapped[str | None] = mapped_column(String(255))
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    listings: Mapped[list[ProductPlatformListing]] = relationship(back_populates="product")


class ProductPlatformListing(Base):
    __tablename__ = "product_platform_listings"
    __table_args__ = (
        UniqueConstraint("platform", "store_name", "msku"),
        CheckConstraint(
            "platform IN ('walmart', 'amazon', 'temu', 'other')",
            name="ck_product_platform_listings_platform_allowed",
        ),
        CheckConstraint(
            "wfs_fee IS NULL OR wfs_fee >= 0",
            name="ck_product_platform_listings_wfs_fee_nonnegative",
        ),
        CheckConstraint(
            "shipping_cost IS NULL OR shipping_cost >= 0",
            name="ck_product_platform_listings_shipping_cost_nonnegative",
        ),
        CheckConstraint(
            "(wfs_fee IS NULL AND shipping_cost IS NULL) OR currency_code IS NOT NULL",
            name="ck_product_platform_listings_money_currency_required",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    msku: Mapped[str] = mapped_column(String(128), nullable=False)
    external_listing_id: Mapped[str | None] = mapped_column(String(255))
    listing_url: Mapped[str | None] = mapped_column(String(2048))
    listing_status: Mapped[str | None] = mapped_column(String(64))
    fulfillment_type: Mapped[str | None] = mapped_column(String(64))
    wfs_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship(back_populates="listings")
