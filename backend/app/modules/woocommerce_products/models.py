"""Storage metadata. External sync and export services are deliberately not registered."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import Base

raw_woocommerce_products = sa.Table(
    "raw_woocommerce_products",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("woo_product_id", sa.BigInteger(), nullable=False),
    sa.Column("sync_run_id", sa.String(128), nullable=False),
    sa.Column("payload_hash", sa.String(64), nullable=False),
    sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
    sa.Column("source_modified_at", sa.DateTime(timezone=True)),
    sa.Column(
        "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.ForeignKeyConstraint(
        ["store_id"], ["sys_woocommerce_stores.id"], name="fk_woo_raw_store", ondelete="RESTRICT"
    ),
    sa.UniqueConstraint("store_id", "woo_product_id", "sync_run_id", name="uq_woo_raw_run_product"),
    sa.UniqueConstraint("id", "store_id", "woo_product_id", name="uq_woo_raw_identity"),
    sa.CheckConstraint("woo_product_id > 0", name="ck_woo_raw_id"),
    sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_woo_raw_hash"),
    sa.CheckConstraint("jsonb_typeof(raw_payload) = 'object'", name="ck_woo_raw_json"),
)
sa.Index(
    "ix_woo_raw_product_time",
    raw_woocommerce_products.c.store_id,
    raw_woocommerce_products.c.woo_product_id,
    raw_woocommerce_products.c.fetched_at,
)

dim_woocommerce_products = sa.Table(
    "dim_woocommerce_products",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("woo_product_id", sa.BigInteger(), nullable=False),
    sa.Column("raw_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("sku", sa.Text()),
    sa.Column("permalink", sa.Text()),
    sa.Column("image_urls", postgresql.JSONB()),
    sa.Column("short_description", sa.Text()),
    sa.Column("description", sa.Text()),
    sa.Column("brands", postgresql.JSONB()),
    sa.Column("categories", postgresql.JSONB()),
    sa.Column("price", sa.Numeric(18, 4)),
    sa.Column("currency_code", sa.String(3)),
    sa.Column("manage_stock", sa.Boolean()),
    sa.Column("stock_quantity", sa.Integer()),
    sa.Column("stock_status", sa.String(32)),
    sa.Column("publish_status", sa.String(32)),
    sa.Column("source_created_at", sa.DateTime(timezone=True)),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("source_modified_at", sa.DateTime(timezone=True)),
    sa.Column(
        "last_synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.ForeignKeyConstraint(
        ["store_id"], ["sys_woocommerce_stores.id"], name="fk_woo_dim_store", ondelete="RESTRICT"
    ),
    sa.ForeignKeyConstraint(
        ["raw_id", "store_id", "woo_product_id"],
        [
            "raw_woocommerce_products.id",
            "raw_woocommerce_products.store_id",
            "raw_woocommerce_products.woo_product_id",
        ],
        name="fk_woo_dim_raw_identity",
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("store_id", "woo_product_id", name="uq_woo_dim_product"),
    sa.CheckConstraint("woo_product_id > 0", name="ck_woo_dim_id"),
    sa.CheckConstraint(
        "price IS NULL OR (price >= 0 AND currency_code IS NOT NULL)", name="ck_woo_dim_price"
    ),
    sa.CheckConstraint(
        "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'", name="ck_woo_dim_currency"
    ),
    sa.CheckConstraint("stock_quantity IS NULL OR stock_quantity >= 0", name="ck_woo_dim_stock"),
    sa.CheckConstraint(
        "image_urls IS NULL OR jsonb_typeof(image_urls) = 'array'", name="ck_woo_dim_image_urls"
    ),
    sa.CheckConstraint(
        "brands IS NULL OR jsonb_typeof(brands) = 'array'", name="ck_woo_dim_brands"
    ),
    sa.CheckConstraint(
        "categories IS NULL OR jsonb_typeof(categories) = 'array'", name="ck_woo_dim_categories"
    ),
)
sa.Index(
    "ix_woo_dim_store_status",
    dim_woocommerce_products.c.store_id,
    dim_woocommerce_products.c.publish_status,
)
sa.Index("ix_woo_dim_sku", dim_woocommerce_products.c.sku)
sa.Index("ix_woo_dim_published", dim_woocommerce_products.c.published_at)

map_woocommerce_listing = sa.Table(
    "map_woocommerce_listing",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("source_account_ref", sa.String(128), nullable=False),
    sa.Column("source_store_id", sa.String(128), nullable=False),
    sa.Column("source_item_id", sa.String(128), nullable=False),
    sa.Column("woo_store_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("woo_product_id", sa.BigInteger(), nullable=False),
    sa.Column("match_method", sa.String(32), nullable=False),
    sa.Column("confirmed_by", sa.String(128), nullable=False),
    sa.Column(
        "confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("initial_raw_id", postgresql.UUID(as_uuid=True)),
    sa.Column("initial_listing_price", sa.Numeric(18, 4)),
    sa.Column("initial_currency_code", sa.String(3)),
    sa.ForeignKeyConstraint(
        ["source_account_ref", "source_store_id", "source_item_id"],
        [
            "dim_walmart_listings.source_account_ref",
            "dim_walmart_listings.store_id",
            "dim_walmart_listings.item_id",
        ],
        name="fk_woo_map_listing",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["woo_store_id", "woo_product_id"],
        ["dim_woocommerce_products.store_id", "dim_woocommerce_products.woo_product_id"],
        name="fk_woo_map_product",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["initial_raw_id", "woo_store_id", "woo_product_id"],
        [
            "raw_woocommerce_products.id",
            "raw_woocommerce_products.store_id",
            "raw_woocommerce_products.woo_product_id",
        ],
        name="fk_woo_map_initial_raw",
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint(
        "source_account_ref",
        "source_store_id",
        "source_item_id",
        "woo_store_id",
        name="uq_woo_map_listing_site",
    ),
    sa.CheckConstraint(
        "match_method IN ('manual_confirmed', 'verified_source', 'publish_result')",
        name="ck_woo_map_method",
    ),
    sa.CheckConstraint(
        "initial_listing_price IS NULL OR (initial_listing_price >= 0 AND "
        "initial_currency_code IS NOT NULL)",
        name="ck_woo_map_initial_price",
    ),
    sa.CheckConstraint(
        "initial_currency_code IS NULL OR initial_currency_code ~ '^[A-Z]{3}$'",
        name="ck_woo_map_currency",
    ),
)
sa.Index(
    "ix_woo_map_product",
    map_woocommerce_listing.c.woo_store_id,
    map_woocommerce_listing.c.woo_product_id,
)

biz_woo_publish_brand_rules = sa.Table(
    "biz_woo_publish_brand_rules",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("source_brand", sa.Text(), nullable=False),
    sa.Column("normalized_brand", sa.Text(), nullable=False),
    sa.Column("target_store_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("target_brand_id", sa.String(128), nullable=False),
    sa.Column("target_category_id", sa.String(128), nullable=False),
    sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("rule_version", sa.Integer(), nullable=False),
    sa.Column("updated_by", sa.String(128), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.ForeignKeyConstraint(
        ["target_store_id"],
        ["sys_woocommerce_stores.id"],
        name="fk_woo_brand_store",
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("normalized_brand", "rule_version", name="uq_woo_brand_version"),
    sa.CheckConstraint(
        "btrim(normalized_brand) <> '' AND btrim(source_brand) <> '' AND "
        "btrim(target_brand_id) <> '' AND btrim(target_category_id) <> ''",
        name="ck_woo_brand_nonblank",
    ),
    sa.CheckConstraint("rule_version > 0", name="ck_woo_brand_version"),
)
sa.Index(
    "uq_woo_brand_current",
    biz_woo_publish_brand_rules.c.normalized_brand,
    unique=True,
    postgresql_where=sa.text("is_current"),
)
sa.Index("ix_woo_brand_target", biz_woo_publish_brand_rules.c.target_store_id)

biz_woo_publish_settings = sa.Table(
    "biz_woo_publish_settings",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("rule_version", sa.Integer(), nullable=False),
    sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("auto_publish_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("listing_status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("price_mode", sa.String(16), nullable=False, server_default="fixed"),
    sa.Column("price_markup", sa.Numeric(18, 4), nullable=False, server_default="2.0000"),
    sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
    sa.Column("stock_quantity", sa.Integer()),
    sa.Column("retry_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="3"),
    sa.Column("submission_interval_days", sa.Integer(), nullable=False, server_default="60"),
    sa.Column("updated_by", sa.String(128), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("rule_version", name="uq_woo_settings_version"),
    sa.CheckConstraint("rule_version > 0", name="ck_woo_settings_version"),
    sa.CheckConstraint("price_mode IN ('original','fixed','percent')", name="ck_woo_settings_mode"),
    sa.CheckConstraint("price_markup >= 0", name="ck_woo_settings_markup"),
    sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_woo_settings_currency"),
    sa.CheckConstraint("stock_quantity IS NULL OR stock_quantity >= 0", name="ck_woo_settings_qty"),
    sa.CheckConstraint("retry_limit BETWEEN 0 AND 20", name="ck_woo_settings_retry"),
    sa.CheckConstraint("submission_interval_days > 0", name="ck_woo_settings_interval"),
)
sa.Index(
    "uq_woo_settings_current",
    biz_woo_publish_settings.c.is_current,
    unique=True,
    postgresql_where=sa.text("is_current"),
)

biz_woo_submission_store_configs = sa.Table(
    "biz_woo_submission_store_configs",
    Base.metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("source_account_ref", sa.String(128), nullable=False),
    sa.Column("source_store_id", sa.String(128), nullable=False),
    sa.Column("submission_store_id", sa.String(128), nullable=False),
    sa.Column("updated_by", sa.String(128), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("source_account_ref", "source_store_id", name="uq_woo_submission_store"),
    sa.CheckConstraint(
        "btrim(source_account_ref) <> '' AND btrim(source_store_id) <> '' AND "
        "btrim(submission_store_id) <> ''",
        name="ck_woo_submission_nonblank",
    ),
)
