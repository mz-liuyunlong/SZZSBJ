"""Add DATA-PAGES-1 DIM, FACT, MART, and rule tables.

Revision ID: 20260917_0011
Revises: 20260916_0010
Create Date: 2026-09-17

This migration creates schema only. It does not backfill data, call external
services, or touch production configuration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260917_0011"
down_revision: str | Sequence[str] | None = "20260916_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BUSINESS_TZ = "America/Los_Angeles"
CHINA_TZ = "Asia/Shanghai"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _amount(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.Numeric(18, 4), nullable=nullable)


def _ratio(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.Numeric(18, 6), nullable=nullable)


def _jsonb(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, postgresql.JSONB(), nullable=nullable)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _raw_ref() -> sa.Column[object]:
    return sa.Column(
        "source_raw_request_ref_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL"),
        nullable=True,
    )


def _business_timezone() -> sa.Column[object]:
    return sa.Column(
        "business_timezone",
        sa.String(64),
        server_default=sa.text(f"'{BUSINESS_TZ}'"),
        nullable=False,
    )


def upgrade() -> None:
    op.drop_constraint(
        "ck_gov_integration_interface_dependencies_dependency_type",
        "gov_integration_interface_dependencies",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_gov_integration_interface_dependencies_dependency_type"),
        "gov_integration_interface_dependencies",
        "dependency_type IN ('requires_sku_ids', 'requires_advertiser_ids')",
    )

    op.create_table(
        "dim_lingxing_stores",
        _uuid("id"),
        sa.Column("source_system", sa.String(32), server_default=sa.text("'lingxing'"), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_name_raw", sa.Text(), nullable=True),
        sa.Column("platform_code_raw", sa.String(64), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("sid", sa.String(128), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("raw_status", sa.String(64), nullable=True),
        sa.Column("is_sync", sa.Boolean(), nullable=True),
        _raw_ref(),
        _ts("source_observed_at"),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("store_id <> ''", name=op.f("ck_dim_lingxing_stores_store_id_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dim_lingxing_stores")),
        sa.UniqueConstraint(
            "source_account_ref",
            "platform_code_raw",
            "store_id",
            name=op.f("uq_dim_lingxing_stores_source_account_ref"),
        ),
    )
    op.create_index(
        "ix_dim_lingxing_stores_platform_store",
        "dim_lingxing_stores",
        ["platform_code", "store_id"],
    )

    op.create_table(
        "dim_walmart_listings",
        _uuid("id"),
        sa.Column("source_system", sa.String(32), server_default=sa.text("'lingxing'"), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("platform_code_raw", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("local_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("item_url", sa.Text(), nullable=True),
        _amount("price_amount"),
        sa.Column("price_currency_code", sa.String(3), nullable=True),
        sa.Column("price_currency_symbol_raw", sa.String(16), nullable=True),
        sa.Column("listing_start_source_raw", sa.Text(), nullable=True),
        sa.Column("listing_start_source_timezone", sa.String(64), nullable=True),
        _ts("listing_start_at_utc"),
        sa.Column("listing_end_source_raw", sa.Text(), nullable=True),
        _ts("listing_end_at_utc"),
        _amount("available_quantity"),
        _amount("wfs_available_quantity"),
        sa.Column("average_rating", sa.Numeric(8, 4), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("gtin", sa.Text(), nullable=True),
        sa.Column("upc", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("raw_status", sa.String(128), nullable=True),
        sa.Column("standard_status", sa.String(64), nullable=True),
        sa.Column("fulfillment_type", sa.String(64), nullable=True),
        sa.Column("fulfillment_type_name", sa.String(128), nullable=True),
        sa.Column("variant_unique_id", sa.Text(), nullable=True),
        sa.Column("business_hash", sa.String(64), nullable=True),
        _raw_ref(),
        _ts("source_observed_at"),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("item_id <> ''", name=op.f("ck_dim_walmart_listings_item_id_not_blank")),
        sa.CheckConstraint("store_id <> ''", name=op.f("ck_dim_walmart_listings_store_id_not_blank")),
        sa.CheckConstraint("price_amount IS NULL OR price_amount >= 0", name=op.f("ck_dim_walmart_listings_price_nonnegative")),
        sa.CheckConstraint("business_hash IS NULL OR char_length(business_hash) = 64", name=op.f("ck_dim_walmart_listings_business_hash_sha256")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dim_walmart_listings")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            name=op.f("uq_dim_walmart_listings_source_account_ref"),
        ),
    )
    op.create_index("ix_dim_walmart_listings_local_sku", "dim_walmart_listings", ["local_sku"])
    op.create_index("ix_dim_walmart_listings_msku", "dim_walmart_listings", ["msku"])
    op.create_index(
        "ix_dim_walmart_listings_store_item",
        "dim_walmart_listings",
        ["store_id", "item_id"],
    )

    op.create_table(
        "dim_walmart_advertisers",
        _uuid("id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("advertiser_name", sa.Text(), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("raw_status", sa.String(64), nullable=True),
        sa.Column("standard_status", sa.String(64), nullable=True),
        _raw_ref(),
        _ts("source_observed_at"),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "advertiser_id <> ''",
            name=op.f("ck_dim_walmart_advertisers_advertiser_id_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dim_walmart_advertisers")),
        sa.UniqueConstraint(
            "source_account_ref",
            "advertiser_id",
            name=op.f("uq_dim_walmart_advertisers_source_account_ref"),
        ),
    )
    op.create_index("ix_dim_walmart_advertisers_store", "dim_walmart_advertisers", ["store_id"])

    op.create_table(
        "ref_store_commission_rule_versions",
        _uuid("id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("commission_rate", sa.Numeric(9, 6), server_default=sa.text("0.15"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("commission_rate >= 0 AND commission_rate < 1", name=op.f("ck_ref_store_commission_rule_versions_rate_range")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_ref_store_commission_rule_versions_effective_period"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ref_store_commission_rule_versions")),
        sa.UniqueConstraint(
            "source_account_ref",
            "platform_code",
            "store_id",
            "rule_version",
            name=op.f("uq_ref_store_commission_rule_versions_source_account_ref"),
        ),
    )
    op.create_index(
        "ix_ref_store_commission_active",
        "ref_store_commission_rule_versions",
        ["source_account_ref", "platform_code", "store_id", "is_active", "effective_from"],
    )

    op.create_table(
        "fact_walmart_sales_item_daily",
        _uuid("id"),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        _business_timezone(),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("platform_code_raw", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("sid", sa.String(128), nullable=True),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        _amount("sales_qty"),
        _amount("order_count"),
        _amount("sales_amount"),
        sa.Column("sales_currency_code", sa.String(3), nullable=True),
        sa.Column("source_date_raw", sa.Text(), nullable=True),
        sa.Column("source_group_key", sa.String(128), nullable=True),
        sa.Column("allocation_status", sa.String(32), server_default=sa.text("'direct'"), nullable=False),
        _jsonb("date_collect_json"),
        _raw_ref(),
        _ts("source_observed_at"),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "allocation_status IN ('direct', 'needs_owner_decision', 'skipped')",
            name=op.f("ck_fact_walmart_sales_item_daily_allocation_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_walmart_sales_item_daily")),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "store_id",
            "item_id",
            name=op.f("uq_fact_walmart_sales_item_daily_business_date_la"),
        ),
    )
    op.create_index("ix_fact_walmart_sales_item_date", "fact_walmart_sales_item_daily", ["item_id", "business_date_la"])
    op.create_index("ix_fact_walmart_sales_store_date", "fact_walmart_sales_item_daily", ["store_id", "business_date_la"])

    _create_order_fact()
    _create_refund_fact()
    _create_ad_fact()
    _create_daily_sales_mart()
    _create_order_profit_mart()
    _create_listing_current_mart()


def _create_order_fact() -> None:
    op.create_table(
        "fact_walmart_order_items",
        _uuid("id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("source_order_id", sa.String(128), nullable=False),
        sa.Column("source_order_line_id", sa.String(128), nullable=True),
        sa.Column("source_line_hash", sa.String(64), nullable=False),
        sa.Column("source_line_ordinal", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        _amount("quantity"),
        sa.Column("source_purchase_at_raw", sa.Text(), nullable=True),
        sa.Column("source_purchase_timezone", sa.String(64), server_default=sa.text(f"'{CHINA_TZ}'"), nullable=False),
        _ts("purchase_at_utc"),
        sa.Column("business_date_la", sa.Date(), nullable=True),
        _business_timezone(),
        sa.Column("order_status_raw", sa.String(64), nullable=True),
        sa.Column("order_sub_status_raw", sa.String(64), nullable=True),
        sa.Column("flow_node_raw", sa.String(64), nullable=True),
        _amount("sales_revenue_amount"),
        sa.Column("sales_revenue_currency_code", sa.String(3), nullable=True),
        _amount("order_total_amount"),
        sa.Column("order_total_currency_code", sa.String(3), nullable=True),
        _amount("discount_amount"),
        sa.Column("discount_currency_code", sa.String(3), nullable=True),
        sa.Column("is_sample_order", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sample_rule_version", sa.String(64), nullable=True),
        _raw_ref(),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("char_length(source_line_hash) = 64", name=op.f("ck_fact_walmart_order_items_source_line_hash_sha256")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_walmart_order_items")),
        sa.UniqueConstraint(
            "source_account_ref",
            "source_order_id",
            "source_line_hash",
            name=op.f("uq_fact_walmart_order_items_source_account_ref"),
        ),
    )
    op.create_index("ix_fact_walmart_order_items_business_date", "fact_walmart_order_items", ["business_date_la"])
    op.create_index("ix_fact_walmart_order_items_store_item", "fact_walmart_order_items", ["store_id", "item_id"])


def _create_refund_fact() -> None:
    op.create_table(
        "fact_walmart_refund_items",
        _uuid("id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("source_return_order_id", sa.String(128), nullable=False),
        sa.Column("source_return_line_id", sa.String(128), nullable=True),
        sa.Column("source_line_hash", sa.String(64), nullable=False),
        sa.Column("source_line_ordinal", sa.Integer(), nullable=False),
        sa.Column("customer_order_id", sa.String(128), nullable=True),
        sa.Column("purchase_order_id", sa.String(128), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("return_type_raw", sa.String(64), nullable=False),
        sa.Column("return_type_name", sa.Text(), nullable=True),
        sa.Column("refund_status_raw", sa.String(64), nullable=True),
        sa.Column("refund_status_standard", sa.String(64), nullable=True),
        sa.Column("return_order_date_raw", sa.Text(), nullable=True),
        _ts("refund_at_utc"),
        sa.Column("business_date_la", sa.Date(), nullable=True),
        _business_timezone(),
        sa.Column("status_time_raw", sa.Text(), nullable=True),
        _ts("status_time_utc"),
        _amount("quantity"),
        _amount("refund_amount"),
        sa.Column("refund_currency_code", sa.String(3), nullable=True),
        sa.Column("tracking_no", sa.Text(), nullable=True),
        _raw_ref(),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("char_length(source_line_hash) = 64", name=op.f("ck_fact_walmart_refund_items_source_line_hash_sha256")),
        sa.CheckConstraint("return_type_raw = 'REFUND'", name=op.f("ck_fact_walmart_refund_items_return_type_refund")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_walmart_refund_items")),
        sa.UniqueConstraint(
            "source_account_ref",
            "source_return_order_id",
            "source_line_hash",
            name=op.f("uq_fact_walmart_refund_items_source_account_ref"),
        ),
    )
    op.create_index("ix_fact_walmart_refund_items_business_date", "fact_walmart_refund_items", ["business_date_la"])
    op.create_index("ix_fact_walmart_refund_items_store_item", "fact_walmart_refund_items", ["store_id", "item_id"])


def _create_ad_fact() -> None:
    op.create_table(
        "fact_walmart_ad_item_sp_daily",
        _uuid("id"),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        _business_timezone(),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("campaign_id", sa.String(128), nullable=True),
        sa.Column("ad_group_id", sa.String(128), nullable=True),
        sa.Column("ad_item_id", sa.String(128), nullable=True),
        sa.Column("source_line_hash", sa.String(64), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=True),
        _amount("ad_spend_amount"),
        sa.Column("ad_spend_currency_code", sa.String(3), nullable=True),
        _amount("attributed_sales_amount"),
        sa.Column("attributed_sales_currency_code", sa.String(3), nullable=True),
        _amount("attributed_orders"),
        _amount("attributed_units"),
        _amount("advertised_sku_sales_amount"),
        sa.Column("advertised_sku_sales_currency_code", sa.String(3), nullable=True),
        _amount("advertised_sku_units"),
        sa.Column("num_ads_clicks", sa.Integer(), nullable=True),
        sa.Column("num_ads_shown", sa.Integer(), nullable=True),
        _ratio("acos"),
        _ratio("roas"),
        _amount("cpc"),
        _ratio("ctr"),
        _ratio("cvr"),
        _raw_ref(),
        _ts("synced_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("char_length(source_line_hash) = 64", name=op.f("ck_fact_walmart_ad_item_sp_daily_source_line_hash_sha256")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_walmart_ad_item_sp_daily")),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "advertiser_id",
            "source_line_hash",
            name=op.f("uq_fact_walmart_ad_item_sp_daily_business_date_la"),
        ),
    )
    op.create_index("ix_fact_walmart_ads_advertiser_date", "fact_walmart_ad_item_sp_daily", ["advertiser_id", "business_date_la"])
    op.create_index("ix_fact_walmart_ads_item_date", "fact_walmart_ad_item_sp_daily", ["item_id", "business_date_la"])


def _create_daily_sales_mart() -> None:
    op.create_table(
        "mart_daily_sales_item_day",
        _uuid("id"),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        _business_timezone(),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("local_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("owner_ref", sa.String(255), nullable=True),
        _amount("sales_qty", nullable=False),
        _amount("order_count", nullable=False),
        _amount("sales_amount", nullable=False),
        sa.Column("sales_currency_code", sa.String(3), nullable=True),
        _amount("sample_amount"),
        _amount("sales_amount_excluding_sample"),
        _amount("return_qty"),
        _amount("refund_amount"),
        sa.Column("refund_currency_code", sa.String(3), nullable=True),
        _ratio("return_rate_30d"),
        _amount("ad_spend_amount"),
        sa.Column("ad_spend_currency_code", sa.String(3), nullable=True),
        _ratio("ad_ratio"),
        _amount("wfs_available_quantity"),
        _amount("wfs_fee_unit_amount"),
        _amount("wfs_fee_total_amount"),
        sa.Column("wfs_fee_currency_code", sa.String(3), nullable=True),
        _amount("purchase_cost_unit_cny"),
        _amount("purchase_cost_total_usd"),
        _amount("first_leg_cost_unit_cny"),
        _amount("first_leg_cost_total_usd"),
        _amount("storage_fee_unit_amount"),
        _amount("storage_fee_total_amount"),
        sa.Column("storage_fee_currency_code", sa.String(3), nullable=True),
        _ratio("exchange_rate"),
        sa.Column("fx_date", sa.Date(), nullable=True),
        sa.Column("fx_source", sa.String(255), nullable=True),
        sa.Column("commission_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column(
            "commission_rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ref_store_commission_rule_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _amount("commission_fee_amount"),
        sa.Column("commission_fee_currency_code", sa.String(3), nullable=True),
        _amount("gross_profit_amount"),
        sa.Column("gross_profit_currency_code", sa.String(3), nullable=True),
        _ratio("gross_margin"),
        _ratio("roi"),
        sa.Column("cost_status", sa.String(32), server_default=sa.text("'missing'"), nullable=False),
        _jsonb("missing_cost_codes_json", nullable=False),
        _jsonb("sales_7d_trend_json", nullable=False),
        _jsonb("source_lineage_json", nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        _ts("calculated_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("cost_status IN ('complete', 'partial', 'missing')", name=op.f("ck_mart_daily_sales_item_day_cost_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_daily_sales_item_day")),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "store_id",
            "item_id",
            name=op.f("uq_mart_daily_sales_item_day_business_date_la"),
        ),
    )
    op.create_index("ix_mart_daily_sales_item_date", "mart_daily_sales_item_day", ["item_id", "business_date_la"])
    op.create_index("ix_mart_daily_sales_store_date", "mart_daily_sales_item_day", ["store_id", "business_date_la"])


def _create_order_profit_mart() -> None:
    op.create_table(
        "mart_order_profit_sku_day",
        _uuid("id"),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        _business_timezone(),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("local_sku", sa.Text(), nullable=False),
        _jsonb("item_ids_json", nullable=False),
        _jsonb("store_ids_json", nullable=False),
        sa.Column("store_count", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        _amount("sales_qty", nullable=False),
        _amount("order_count", nullable=False),
        _amount("sales_amount", nullable=False),
        sa.Column("sales_currency_code", sa.String(3), nullable=True),
        _amount("refund_amount"),
        _amount("ad_spend_amount"),
        _amount("commission_fee_amount"),
        _amount("wfs_fee_total_amount"),
        _amount("purchase_cost_total_usd"),
        _amount("first_leg_cost_total_usd"),
        _amount("storage_fee_total_amount"),
        _amount("gross_profit_amount"),
        sa.Column("gross_profit_currency_code", sa.String(3), nullable=True),
        _ratio("gross_margin"),
        _ratio("roi"),
        sa.Column("cost_status", sa.String(32), server_default=sa.text("'missing'"), nullable=False),
        _jsonb("missing_cost_codes_json", nullable=False),
        _jsonb("source_lineage_json", nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        _ts("calculated_at", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("cost_status IN ('complete', 'partial', 'missing')", name=op.f("ck_mart_order_profit_sku_day_cost_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_order_profit_sku_day")),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "local_sku",
            name=op.f("uq_mart_order_profit_sku_day_business_date_la"),
        ),
    )
    op.create_index("ix_mart_order_profit_sku_date", "mart_order_profit_sku_day", ["local_sku", "business_date_la"])


def _create_listing_current_mart() -> None:
    op.create_table(
        "mart_listing_management_current",
        _uuid("id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("local_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("item_url", sa.Text(), nullable=True),
        sa.Column("owner_ref", sa.String(255), nullable=True),
        sa.Column("product_grade", sa.String(64), nullable=True),
        _jsonb("tags_json", nullable=True),
        _amount("strike_price_amount"),
        sa.Column("strike_price_currency_code", sa.String(3), nullable=True),
        _amount("sale_price_amount"),
        sa.Column("sale_price_currency_code", sa.String(3), nullable=True),
        sa.Column("listing_status", sa.String(64), nullable=True),
        sa.Column("lifecycle_status", sa.String(64), nullable=True),
        _ts("listing_start_at_utc"),
        sa.Column("category", sa.Text(), nullable=True),
        _amount("wfs_available_quantity"),
        _amount("available_quantity"),
        _amount("inbound_quantity"),
        _amount("sales_7d", nullable=False),
        _amount("sales_14d", nullable=False),
        _amount("sales_30d", nullable=False),
        _amount("ad_spend_30d_amount"),
        sa.Column("ad_spend_currency_code", sa.String(3), nullable=True),
        sa.Column("buybox_status", sa.String(64), nullable=True),
        sa.Column("walmart_seller", sa.Text(), nullable=True),
        sa.Column("is_hijacked", sa.Boolean(), nullable=True),
        sa.Column("average_rating", sa.Numeric(8, 4), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        _amount("wfs_fee_amount"),
        sa.Column("wfs_fee_currency_code", sa.String(3), nullable=True),
        sa.Column("gtin", sa.Text(), nullable=True),
        sa.Column("upc", sa.Text(), nullable=True),
        _jsonb("gpt_analysis_links_json", nullable=True),
        _jsonb("source_lineage_json", nullable=True),
        _ts("calculated_at", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_listing_management_current")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            name=op.f("uq_mart_listing_management_current_source_account_ref"),
        ),
    )
    op.create_index("ix_mart_listing_current_local_sku", "mart_listing_management_current", ["local_sku"])
    op.create_index("ix_mart_listing_current_store_item", "mart_listing_management_current", ["store_id", "item_id"])


def downgrade() -> None:
    op.drop_index("ix_mart_listing_current_store_item", table_name="mart_listing_management_current")
    op.drop_index("ix_mart_listing_current_local_sku", table_name="mart_listing_management_current")
    op.drop_table("mart_listing_management_current")

    op.drop_index("ix_mart_order_profit_sku_date", table_name="mart_order_profit_sku_day")
    op.drop_table("mart_order_profit_sku_day")

    op.drop_index("ix_mart_daily_sales_store_date", table_name="mart_daily_sales_item_day")
    op.drop_index("ix_mart_daily_sales_item_date", table_name="mart_daily_sales_item_day")
    op.drop_table("mart_daily_sales_item_day")

    op.drop_index("ix_fact_walmart_ads_item_date", table_name="fact_walmart_ad_item_sp_daily")
    op.drop_index(
        "ix_fact_walmart_ads_advertiser_date",
        table_name="fact_walmart_ad_item_sp_daily",
    )
    op.drop_table("fact_walmart_ad_item_sp_daily")

    op.drop_index("ix_fact_walmart_refund_items_store_item", table_name="fact_walmart_refund_items")
    op.drop_index(
        "ix_fact_walmart_refund_items_business_date",
        table_name="fact_walmart_refund_items",
    )
    op.drop_table("fact_walmart_refund_items")

    op.drop_index("ix_fact_walmart_order_items_store_item", table_name="fact_walmart_order_items")
    op.drop_index(
        "ix_fact_walmart_order_items_business_date",
        table_name="fact_walmart_order_items",
    )
    op.drop_table("fact_walmart_order_items")

    op.drop_index("ix_fact_walmart_sales_store_date", table_name="fact_walmart_sales_item_daily")
    op.drop_index("ix_fact_walmart_sales_item_date", table_name="fact_walmart_sales_item_daily")
    op.drop_table("fact_walmart_sales_item_daily")

    op.drop_index("ix_ref_store_commission_active", table_name="ref_store_commission_rule_versions")
    op.drop_table("ref_store_commission_rule_versions")

    op.drop_index("ix_dim_walmart_advertisers_store", table_name="dim_walmart_advertisers")
    op.drop_table("dim_walmart_advertisers")

    op.drop_index("ix_dim_walmart_listings_store_item", table_name="dim_walmart_listings")
    op.drop_index("ix_dim_walmart_listings_msku", table_name="dim_walmart_listings")
    op.drop_index("ix_dim_walmart_listings_local_sku", table_name="dim_walmart_listings")
    op.drop_table("dim_walmart_listings")

    op.drop_index("ix_dim_lingxing_stores_platform_store", table_name="dim_lingxing_stores")
    op.drop_table("dim_lingxing_stores")

    op.drop_constraint(
        "ck_gov_integration_interface_dependencies_dependency_type",
        "gov_integration_interface_dependencies",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_gov_integration_interface_dependencies_dependency_type"),
        "gov_integration_interface_dependencies",
        "dependency_type = 'requires_sku_ids'",
    )
