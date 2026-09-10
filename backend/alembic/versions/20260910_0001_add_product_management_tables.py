"""Add Product Management core tables.

Revision ID: 20260910_0001
Revises:
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("product_type", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("grade", sa.String(length=64), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("declared_cn_name", sa.String(length=255), nullable=True),
        sa.Column("declared_en_name", sa.String(length=255), nullable=True),
        sa.Column("material_cn", sa.String(length=255), nullable=True),
        sa.Column("material_en", sa.String(length=255), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(purchase_price IS NULL AND currency_code IS NULL) OR "
            "(purchase_price IS NOT NULL AND currency_code IS NOT NULL)",
            name=op.f("ck_products_purchase_price_currency_pair"),
        ),
        sa.CheckConstraint(
            "purchase_price IS NULL OR purchase_price >= 0",
            name=op.f("ck_products_purchase_price_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_table(
        "product_platform_listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("store_name", sa.String(length=255), nullable=False),
        sa.Column("msku", sa.String(length=128), nullable=False),
        sa.Column("external_listing_id", sa.String(length=255), nullable=True),
        sa.Column("listing_url", sa.String(length=2048), nullable=True),
        sa.Column("listing_status", sa.String(length=64), nullable=True),
        sa.Column("fulfillment_type", sa.String(length=64), nullable=True),
        sa.Column("wfs_fee", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("shipping_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "platform IN ('walmart', 'amazon', 'temu', 'other')",
            name=op.f("ck_product_platform_listings_platform_allowed"),
        ),
        sa.CheckConstraint(
            "wfs_fee IS NULL OR wfs_fee >= 0",
            name=op.f("ck_product_platform_listings_wfs_fee_nonnegative"),
        ),
        sa.CheckConstraint(
            "shipping_cost IS NULL OR shipping_cost >= 0",
            name=op.f("ck_product_platform_listings_shipping_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "(wfs_fee IS NULL AND shipping_cost IS NULL) OR currency_code IS NOT NULL",
            name=op.f("ck_product_platform_listings_money_currency_required"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_platform_listings_product_id_products"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_platform_listings")),
        sa.UniqueConstraint(
            "platform",
            "store_name",
            "msku",
            name=op.f("uq_product_platform_listings_platform"),
        ),
    )
    op.create_index(
        op.f("ix_product_platform_listings_product_id"),
        "product_platform_listings",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_product_platform_listings_product_id"),
        table_name="product_platform_listings",
    )
    op.drop_table("product_platform_listings")
    op.drop_table("products")
