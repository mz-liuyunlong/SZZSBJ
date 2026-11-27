"""Additive SKU/advertising/Listing progress data foundation (schema only)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import Base

LingxingSkuSourceSnapshot_table = sa.Table(
    "dwd_lingxing_sku_source_snapshots",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column("source_account_ref", sa.String(128), nullable=False),
    sa.Column("sku_identity_id", sa.Uuid(), nullable=False),
    sa.Column("source_interface", sa.String(128), nullable=False),
    sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
    sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=False),
    sa.Column("source_item_ordinal", sa.Integer(), nullable=False),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_payload_hash", sa.String(64), nullable=False),
    sa.Column("parser_version", sa.String(128), nullable=False),
    sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("source_sku_code", sa.String(255), nullable=True),
    sa.Column("source_product_name", sa.Text(), nullable=True),
    sa.Column("source_picture_url", sa.Text(), nullable=True),
    sa.Column("source_developer_name", sa.Text(), nullable=True),
    sa.Column("source_developer_uid", sa.String(255), nullable=True),
    sa.Column("source_create_time_raw", sa.BigInteger(), nullable=True),
    sa.Column("source_update_time_raw", sa.BigInteger(), nullable=True),
    sa.Column("source_open_status", sa.Integer(), nullable=True),
    sa.Column("source_product_status", sa.Integer(), nullable=True),
    sa.Column("source_status_text", sa.Text(), nullable=True),
    sa.Column("source_category_id", sa.String(255), nullable=True),
    sa.Column("source_category_name", sa.Text(), nullable=True),
    sa.Column("source_category_path", sa.Text(), nullable=True),
    sa.Column("source_brand_id", sa.String(255), nullable=True),
    sa.Column("source_brand_name", sa.Text(), nullable=True),
    sa.Column("source_spu_id", sa.String(255), nullable=True),
    sa.Column("source_spu_code", sa.String(255), nullable=True),
    sa.Column("source_is_combo_raw", sa.Integer(), nullable=True),
    sa.Column("source_sku_identifier", sa.Text(), nullable=True),
    sa.Column("source_unit", sa.Text(), nullable=True),
    sa.Column("source_description", sa.Text(), nullable=True),
    sa.Column("source_model", sa.Text(), nullable=True),
    sa.Column("source_product_remark", sa.Text(), nullable=True),
    sa.Column("source_purchaser_uid", sa.String(255), nullable=True),
    sa.Column("source_purchaser_name", sa.Text(), nullable=True),
    sa.Column("source_purchase_remark", sa.Text(), nullable=True),
    sa.Column("source_purchase_1688_remark", sa.Text(), nullable=True),
    sa.Column("source_purchase_price_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_purchase_delivery_days", sa.Integer(), nullable=True),
    sa.Column("source_purchase_transport_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_currency_raw", sa.String(128), nullable=True),
    sa.Column("source_purchase_material", sa.Text(), nullable=True),
    sa.Column("source_customs_export_name", sa.Text(), nullable=True),
    sa.Column("source_customs_import_name", sa.Text(), nullable=True),
    sa.Column("source_customs_import_price", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_export_hs_code", sa.Text(), nullable=True),
    sa.Column("source_import_hs_code", sa.Text(), nullable=True),
    sa.Column("source_customs_tax_rate", sa.Numeric(18, 6), nullable=True),
    sa.Column("source_cg_box_height", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_box_length", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_box_weight", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_box_width", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_package_height", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_package_length", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_package_width", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_product_gross_weight", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_product_height", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_product_length", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_product_net_weight", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_product_width", sa.Numeric(18, 4), nullable=True),
    sa.Column("source_cg_box_pcs", sa.Integer(), nullable=True),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint(
        "source_interface IN ('productList', 'batchGetProductInfo', 'productInfo')",
        name="sku_src_interface_ck",
    ),
    sa.CheckConstraint("source_item_ordinal >= 0", name="sku_src_ordinal_ck"),
    sa.CheckConstraint("char_length(source_payload_hash) = 64", name="sku_src_hash_ck"),
    sa.UniqueConstraint(
        "source_account_ref",
        "sku_identity_id",
        "source_interface",
        "id",
        name="uq_sku_src_snapshot_identity",
    ),
    sa.UniqueConstraint(
        "source_account_ref",
        "source_interface",
        "source_raw_request_ref_id",
        "source_item_ordinal",
        name="uq_sku_src_raw_ordinal",
    ),
)
sa.Index(
    "ix_sku_src_snapshot_seen",
    LingxingSkuSourceSnapshot_table.c.source_account_ref,
    LingxingSkuSourceSnapshot_table.c.sku_identity_id,
    LingxingSkuSourceSnapshot_table.c.source_interface,
    LingxingSkuSourceSnapshot_table.c.source_observed_at,
)


class LingxingSkuSourceSnapshot(Base):
    __table__ = LingxingSkuSourceSnapshot_table


LingxingSkuSourceCurrent_table = sa.Table(
    "dwd_lingxing_sku_source_current",
    Base.metadata,
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("sku_identity_id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column("source_interface", sa.String(128), primary_key=True, nullable=False),
    sa.Column("snapshot_id", sa.Uuid(), nullable=False),
    sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_raw_request_ref_id", sa.Uuid(), nullable=False),
    sa.Column("last_item_ordinal", sa.Integer(), nullable=False),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.ForeignKeyConstraint(
        ["source_account_ref", "sku_identity_id", "source_interface", "snapshot_id"],
        [
            "dwd_lingxing_sku_source_snapshots.source_account_ref",
            "dwd_lingxing_sku_source_snapshots.sku_identity_id",
            "dwd_lingxing_sku_source_snapshots.source_interface",
            "dwd_lingxing_sku_source_snapshots.id",
        ],
        name="fk_sku_source_current_snapshot",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("last_item_ordinal >= 0", name="sku_src_cur_ordinal_ck"),
)


class LingxingSkuSourceCurrent(Base):
    __table__ = LingxingSkuSourceCurrent_table


LingxingSkuSupplierQuoteExtension_table = sa.Table(
    "dwd_lingxing_sku_supplier_quotes_ext",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "snapshot_id",
        sa.Uuid(),
        sa.ForeignKey("dwd_lingxing_sku_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("source_ordinal", sa.Integer(), nullable=False),
    sa.Column("source_quote_id", sa.String(255), nullable=True),
    sa.Column("source_product_id", sa.String(255), nullable=True),
    sa.Column("supplier_id", sa.String(255), nullable=True),
    sa.Column("supplier_code", sa.Text(), nullable=True),
    sa.Column("supplier_name", sa.Text(), nullable=True),
    sa.Column("is_primary_raw", sa.Integer(), nullable=True),
    sa.Column("delivery_days", sa.Integer(), nullable=True),
    sa.Column("price_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("currency_symbol_raw", sa.String(128), nullable=True),
    sa.Column("quote_remark", sa.Text(), nullable=True),
    sa.Column("supplier_product_urls_json", postgresql.JSONB(), nullable=True),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.UniqueConstraint("snapshot_id", "source_ordinal", name="uq_sku_supplier_quote_ordinal"),
    sa.CheckConstraint("source_ordinal >= 0", name="sku_supplier_quote_ordinal_ck"),
)
sa.Index("ix_sku_supplier_quote_supplier", LingxingSkuSupplierQuoteExtension_table.c.supplier_id)


class LingxingSkuSupplierQuoteExtension(Base):
    __table__ = LingxingSkuSupplierQuoteExtension_table


LingxingSkuSupplierTierExtension_table = sa.Table(
    "dwd_lingxing_sku_supplier_tiers_ext",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "supplier_quote_id",
        sa.Uuid(),
        sa.ForeignKey("dwd_lingxing_sku_supplier_quotes_ext.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("quote_currency_ordinal", sa.Integer(), nullable=False),
    sa.Column("tier_ordinal", sa.Integer(), nullable=False),
    sa.Column("currency_raw", sa.String(128), nullable=True),
    sa.Column("currency_symbol_raw", sa.String(128), nullable=True),
    sa.Column("is_tax_raw", sa.Integer(), nullable=True),
    sa.Column("tax_rate", sa.Numeric(18, 6), nullable=True),
    sa.Column("moq", sa.Integer(), nullable=True),
    sa.Column("price_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("price_with_tax_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.UniqueConstraint(
        "supplier_quote_id",
        "quote_currency_ordinal",
        "tier_ordinal",
        name="uq_sku_supplier_tier_ordinal",
    ),
    sa.CheckConstraint(
        "quote_currency_ordinal >= 0 AND tier_ordinal >= 0", name="sku_supplier_tier_ordinal_ck"
    ),
)


class LingxingSkuSupplierTierExtension(Base):
    __table__ = LingxingSkuSupplierTierExtension_table


LingxingSkuCountryLogisticsExtension_table = sa.Table(
    "dwd_lingxing_sku_country_logistics_ext",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "snapshot_id",
        sa.Uuid(),
        sa.ForeignKey("dwd_lingxing_sku_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("relation_ordinal", sa.Integer(), nullable=False),
    sa.Column("country_code", sa.String(16), nullable=False),
    sa.Column("import_hs_code", sa.Text(), nullable=True),
    sa.Column("tax_rate", sa.Numeric(18, 6), nullable=True),
    sa.Column("transport_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("transport_currency_raw", sa.String(128), nullable=True),
    sa.Column("clearance_price_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("clearance_currency_raw", sa.String(128), nullable=True),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.UniqueConstraint(
        "snapshot_id", "relation_ordinal", "country_code", name="uq_sku_country_logistics_ordinal"
    ),
    sa.CheckConstraint("relation_ordinal >= 0", name="sku_country_logistics_ord_ck"),
)


class LingxingSkuCountryLogisticsExtension(Base):
    __table__ = LingxingSkuCountryLogisticsExtension_table


WalmartAdAccountStoreMapping_table = sa.Table(
    "biz_walmart_ad_account_store_mapping",
    Base.metadata,
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("advertiser_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("store_id", sa.String(128), nullable=True),
    sa.Column(
        "mapping_status", sa.String(32), nullable=False, server_default=sa.text("'unmapped'")
    ),
    sa.Column("source_advertiser_name", sa.Text(), nullable=True),
    sa.Column("source_status_raw", sa.String(128), nullable=True),
    sa.Column("source_seller_name", sa.Text(), nullable=True),
    sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
    sa.Column("source_blob_id", sa.Uuid(), nullable=True),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("confirmed_by", sa.String(255), nullable=True),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint(
        "mapping_status IN ('unmapped', 'confirmed', 'ambiguous', 'rejected')",
        name="ad_account_map_status_ck",
    ),
    sa.CheckConstraint(
        (
            "mapping_status <> 'confirmed' OR (store_id IS NOT NULL AND evidence_json "
            "IS NOT NULL AND confirmed_at IS NOT NULL)"
        ),
        name="ad_account_map_evidence_ck",
    ),
)
sa.Index(
    "ix_ad_account_store_mapping",
    WalmartAdAccountStoreMapping_table.c.source_account_ref,
    WalmartAdAccountStoreMapping_table.c.store_id,
)


class WalmartAdAccountStoreMapping(Base):
    __table__ = WalmartAdAccountStoreMapping_table


WalmartAdItemConfigExtension_table = sa.Table(
    "dwd_walmart_ad_item_config_ext",
    Base.metadata,
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("advertiser_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("campaign_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("ad_group_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("ad_item_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("item_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("campaign_type_raw", sa.String(128), nullable=True),
    sa.Column("campaign_and_targeting_type", sa.String(128), nullable=True),
    sa.Column("campaign_name", sa.Text(), nullable=True),
    sa.Column("campaign_status_raw", sa.String(128), nullable=True),
    sa.Column("ad_group_name", sa.Text(), nullable=True),
    sa.Column("ad_group_status_raw", sa.String(128), nullable=True),
    sa.Column("ad_name", sa.Text(), nullable=True),
    sa.Column("ad_status_raw", sa.String(128), nullable=True),
    sa.Column("bid_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("suggested_bid_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("review_status_raw", sa.String(128), nullable=True),
    sa.Column("review_reason", sa.Text(), nullable=True),
    sa.Column("entity_created_at_raw", sa.Text(), nullable=True),
    sa.Column("add_date_raw", sa.Text(), nullable=True),
    sa.Column("source_advertiser_name", sa.Text(), nullable=True),
    sa.Column("source_seller_name", sa.Text(), nullable=True),
    sa.Column("source_image_url", sa.Text(), nullable=True),
    sa.Column("source_item_url", sa.Text(), nullable=True),
    sa.Column("is_apply_time_raw", sa.String(128), nullable=True),
    sa.Column("benchmark_value", sa.Numeric(18, 4), nullable=True),
    sa.Column("applied_template_json", postgresql.JSONB(), nullable=True),
    sa.Column("bid_currency_code", sa.String(3), nullable=True),
    sa.Column("source_key", sa.Text(), nullable=True),
    sa.Column("source_blob_id", sa.Uuid(), nullable=False),
    sa.Column("source_ordinal", sa.Integer(), nullable=False),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint("source_ordinal >= 0", name="ad_config_ordinal_ck"),
)
sa.Index(
    "ix_ad_config_item_scope",
    WalmartAdItemConfigExtension_table.c.source_account_ref,
    WalmartAdItemConfigExtension_table.c.item_id,
)
sa.Index(
    "ix_ad_config_account_seen",
    WalmartAdItemConfigExtension_table.c.source_account_ref,
    WalmartAdItemConfigExtension_table.c.advertiser_id,
    WalmartAdItemConfigExtension_table.c.source_observed_at,
)


class WalmartAdItemConfigExtension(Base):
    __table__ = WalmartAdItemConfigExtension_table


WalmartAdItemDailyExtension_table = sa.Table(
    "fact_walmart_ad_item_sp_daily_ext",
    Base.metadata,
    sa.Column("business_date_la", sa.Date(), primary_key=True, nullable=False),
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("advertiser_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("source_line_hash", sa.String(64), primary_key=True, nullable=False),
    sa.Column("aov_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("cpa_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("other_sku_sales_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("other_sku_units", sa.Numeric(18, 4), nullable=True),
    sa.Column("ntb_order_rate", sa.Numeric(18, 6), nullable=True),
    sa.Column("ntb_orders", sa.Numeric(18, 4), nullable=True),
    sa.Column("ntb_orders_percent", sa.Numeric(18, 6), nullable=True),
    sa.Column("ntb_revenue_amount", sa.Numeric(18, 4), nullable=True),
    sa.Column("ntb_revenue_percent", sa.Numeric(18, 6), nullable=True),
    sa.Column("ntb_units", sa.Numeric(18, 4), nullable=True),
    sa.Column("ntb_units_percent", sa.Numeric(18, 6), nullable=True),
    sa.Column("currency_code", sa.String(3), nullable=True),
    sa.Column("source_blob_id", sa.Uuid(), nullable=False),
    sa.Column("source_ordinal", sa.Integer(), nullable=False),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint("source_ordinal >= 0", name="ad_metric_ordinal_ck"),
    sa.CheckConstraint("char_length(source_line_hash) = 64", name="ad_metric_hash_ck"),
)
sa.Index(
    "ix_ad_daily_ext_scope",
    WalmartAdItemDailyExtension_table.c.source_account_ref,
    WalmartAdItemDailyExtension_table.c.business_date_la,
)


class WalmartAdItemDailyExtension(Base):
    __table__ = WalmartAdItemDailyExtension_table


ListingAdStatusCurrent_table = sa.Table(
    "mart_listing_ad_status_current",
    Base.metadata,
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("store_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("item_id", sa.String(128), primary_key=True, nullable=False),
    sa.Column("ad_enabled", sa.Boolean(), nullable=True),
    sa.Column("ad_status_checked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
    sa.Column("rule_version", sa.String(128), nullable=True),
    sa.Column("unknown_reason", sa.Text(), nullable=True),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint(
        (
            "ad_enabled IS NULL OR (ad_status_checked_at IS NOT NULL AND "
            "source_observed_at IS NOT NULL AND evidence_json IS NOT NULL AND "
            "rule_version IS NOT NULL)"
        ),
        name="listing_ad_status_evidence_ck",
    ),
)
sa.Index(
    "ix_listing_ad_status_scope",
    ListingAdStatusCurrent_table.c.source_account_ref,
    ListingAdStatusCurrent_table.c.store_id,
    ListingAdStatusCurrent_table.c.ad_enabled,
)


class ListingAdStatusCurrent(Base):
    __table__ = ListingAdStatusCurrent_table


NewProductSkuProgress_table = sa.Table(
    "biz_new_product_sku_progress",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column("source_account_ref", sa.String(128), nullable=False),
    sa.Column("sku_identity_id", sa.Uuid(), nullable=False),
    sa.Column(
        "progress_status", sa.String(32), nullable=False, server_default=sa.text("'in_progress'")
    ),
    sa.Column("auto_progress_status", sa.String(32), nullable=True),
    sa.Column("manual_progress_status", sa.String(32), nullable=True),
    sa.Column("status_source", sa.String(16), nullable=False, server_default=sa.text("'system'")),
    sa.Column("manual_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("reason_type", sa.String(128), nullable=True),
    sa.Column("remark", sa.Text(), nullable=True),
    sa.Column("progress_owner_ref", sa.String(255), nullable=True),
    sa.Column("expected_completed_on", sa.Date(), nullable=True),
    sa.Column("next_follow_up_on", sa.Date(), nullable=True),
    sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("entry_source", sa.String(32), nullable=False, server_default=sa.text("'system'")),
    sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("exit_reason", sa.Text(), nullable=True),
    sa.Column("auto_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("auto_evidence_json", postgresql.JSONB(), nullable=True),
    sa.Column("auto_rule_version", sa.String(128), nullable=True),
    sa.Column("manual_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("manual_updated_by", sa.String(255), nullable=True),
    sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("updated_by", sa.String(255), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("source_account_ref", "sku_identity_id", name="uq_sku_progress_scope"),
    sa.CheckConstraint(
        "progress_status IN ('in_progress', 'completed', 'paused', 'terminated')",
        name="sku_progress_status_ck",
    ),
    sa.CheckConstraint(
        (
            "auto_progress_status IS NULL OR auto_progress_status IN ('in_progress', "
            "'completed', 'paused', 'terminated')"
        ),
        name="sku_auto_status_ck",
    ),
    sa.CheckConstraint(
        (
            "manual_progress_status IS NULL OR manual_progress_status IN "
            "('in_progress', 'completed', 'paused', 'terminated')"
        ),
        name="sku_manual_status_ck",
    ),
    sa.CheckConstraint("status_source IN ('system', 'manual')", name="sku_status_source_ck"),
    sa.CheckConstraint(
        (
            "NOT manual_locked OR (manual_progress_status IS NOT NULL AND "
            "status_source = 'manual' AND progress_status = manual_progress_status)"
        ),
        name="sku_manual_lock_ck",
    ),
    sa.CheckConstraint(
        (
            "status_source <> 'manual' OR (manual_progress_status IS NOT NULL AND "
            "progress_status = manual_progress_status AND manual_updated_by IS NOT "
            "NULL AND manual_updated_at IS NOT NULL AND remark IS NOT NULL AND "
            "char_length(trim(remark)) > 0 AND (progress_status NOT IN "
            "('paused','terminated') OR (reason_type IS NOT NULL AND "
            "char_length(trim(reason_type)) > 0)))"
        ),
        name="sku_manual_evidence_ck",
    ),
    sa.CheckConstraint("version >= 1", name="sku_progress_version_ck"),
    sa.CheckConstraint("entry_source IN ('system', 'manual')", name="sku_progress_entry_ck"),
)
sa.Index(
    "ix_sku_progress_scope_status",
    NewProductSkuProgress_table.c.source_account_ref,
    NewProductSkuProgress_table.c.progress_status,
)
sa.Index(
    "ix_sku_progress_owner_followup",
    NewProductSkuProgress_table.c.source_account_ref,
    NewProductSkuProgress_table.c.progress_owner_ref,
    NewProductSkuProgress_table.c.next_follow_up_on,
)


class NewProductSkuProgress(Base):
    __table__ = NewProductSkuProgress_table


NewProductSkuPurchasePlan_table = sa.Table(
    "biz_new_product_sku_purchase_plans",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "sku_progress_id",
        sa.Uuid(),
        sa.ForeignKey("biz_new_product_sku_progress.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("store_id", sa.String(128), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column(
        "submission_status", sa.String(32), nullable=False, server_default=sa.text("'pending'")
    ),
    sa.Column("batch_id", sa.Uuid(), nullable=True),
    sa.Column("lingxing_plan_sn", sa.String(255), nullable=True),
    sa.Column("lingxing_plan_line_id", sa.String(255), nullable=True),
    sa.Column("submitted_by", sa.String(255), nullable=True),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("idempotency_key", sa.String(255), nullable=False),
    sa.Column("request_ref", sa.String(255), nullable=True),
    sa.Column("response_status", sa.String(128), nullable=True),
    sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("error_code", sa.String(128), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("cancellation_status", sa.String(32), nullable=True),
    sa.Column("cancellation_reason", sa.Text(), nullable=True),
    sa.Column("cancelled_by", sa.String(255), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("idempotency_key", name="uq_sku_purchase_idempotency"),
    sa.UniqueConstraint("sku_progress_id", "id", name="uq_sku_purchase_progress_id"),
    sa.CheckConstraint("quantity = 20", name="sku_purchase_qty_ck"),
    sa.CheckConstraint("retry_count >= 0", name="sku_purchase_retry_ck"),
    sa.CheckConstraint(
        "submission_status IN ('pending', 'submitting', 'unknown', 'submitted', 'failed')",
        name="sku_purchase_submit_ck",
    ),
    sa.CheckConstraint(
        (
            "cancellation_status IS NULL OR cancellation_status IN ('requested', "
            "'unknown', 'failed', 'confirmed')"
        ),
        name="sku_purchase_cancel_ck",
    ),
    sa.CheckConstraint(
        (
            "submission_status <> 'submitted' OR (lingxing_plan_sn IS NOT NULL AND "
            "submitted_at IS NOT NULL)"
        ),
        name="sku_purchase_submitted_ck",
    ),
    sa.CheckConstraint(
        "cancellation_status IS DISTINCT FROM 'confirmed' OR cancelled_at IS NOT NULL",
        name="sku_purchase_cancelled_ck",
    ),
)
sa.Index(
    "uq_sku_purchase_active_store",
    NewProductSkuPurchasePlan_table.c.sku_progress_id,
    NewProductSkuPurchasePlan_table.c.store_id,
    unique=True,
    postgresql_where=sa.text(
        "submission_status IN ('pending','submitting','unknown','submitted') AND "
        "cancellation_status IS DISTINCT FROM 'confirmed'"
    ),
)
sa.Index("ix_sku_purchase_plan_sn", NewProductSkuPurchasePlan_table.c.lingxing_plan_sn)
sa.Index("ix_sku_purchase_batch", NewProductSkuPurchasePlan_table.c.batch_id)


class NewProductSkuPurchasePlan(Base):
    __table__ = NewProductSkuPurchasePlan_table


NewProductIndependentSiteSubmission_table = sa.Table(
    "biz_new_product_independent_site_submissions",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "sku_progress_id",
        sa.Uuid(),
        sa.ForeignKey("biz_new_product_sku_progress.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("target_scope", sa.String(16), nullable=False),
    sa.Column("store_id", sa.String(128), nullable=True),
    sa.Column("item_id", sa.String(128), nullable=True),
    sa.Column(
        "submission_status",
        sa.String(32),
        nullable=False,
        server_default=sa.text("'not_submitted'"),
    ),
    sa.Column("submission_method", sa.String(32), nullable=True),
    sa.Column("external_product_id", sa.String(255), nullable=True),
    sa.Column("external_product_url", sa.Text(), nullable=True),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("submitted_by", sa.String(255), nullable=True),
    sa.Column("failure_reason", sa.Text(), nullable=True),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("revoked_by", sa.String(255), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.CheckConstraint("target_scope IN ('sku', 'listing')", name="sku_site_scope_ck"),
    sa.CheckConstraint(
        (
            "(target_scope = 'sku' AND store_id IS NULL AND item_id IS NULL) OR "
            "(target_scope = 'listing' AND store_id IS NOT NULL AND item_id IS NOT "
            "NULL)"
        ),
        name="sku_site_scope_identity_ck",
    ),
    sa.CheckConstraint(
        "submission_status IN ('not_submitted', 'submitted', 'failed', 'revoked')",
        name="sku_site_status_ck",
    ),
    sa.CheckConstraint(
        "submission_method IS NULL OR submission_method IN ('manual', 'system')",
        name="sku_site_method_ck",
    ),
    sa.CheckConstraint(
        "submission_status <> 'submitted' OR submitted_at IS NOT NULL",
        name="sku_site_submit_time_ck",
    ),
)
sa.Index(
    "uq_sku_site_scope_sku",
    NewProductIndependentSiteSubmission_table.c.sku_progress_id,
    unique=True,
    postgresql_where=sa.text("target_scope = 'sku'"),
)
sa.Index(
    "uq_sku_site_scope_listing",
    NewProductIndependentSiteSubmission_table.c.sku_progress_id,
    NewProductIndependentSiteSubmission_table.c.store_id,
    NewProductIndependentSiteSubmission_table.c.item_id,
    unique=True,
    postgresql_where=sa.text("target_scope = 'listing'"),
)


class NewProductIndependentSiteSubmission(Base):
    __table__ = NewProductIndependentSiteSubmission_table


NewProductSkuProgressEvent_table = sa.Table(
    "biz_new_product_sku_progress_events",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "sku_progress_id",
        sa.Uuid(),
        sa.ForeignKey("biz_new_product_sku_progress.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("event_type", sa.String(128), nullable=False),
    sa.Column("actor_type", sa.String(16), nullable=False),
    sa.Column("actor_ref", sa.String(255), nullable=True),
    sa.Column("event_key", sa.String(255), nullable=False),
    sa.Column("before_json", postgresql.JSONB(), nullable=True),
    sa.Column("after_json", postgresql.JSONB(), nullable=True),
    sa.Column("reason_type", sa.String(128), nullable=True),
    sa.Column("remark", sa.Text(), nullable=True),
    sa.Column("source_evidence_json", postgresql.JSONB(), nullable=True),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("sku_progress_id", "event_key", name="uq_sku_progress_event_key"),
    sa.CheckConstraint("actor_type IN ('system', 'manual')", name="sku_progress_event_actor_ck"),
    sa.CheckConstraint(
        "actor_type <> 'manual' OR actor_ref IS NOT NULL", name="sku_progress_event_actor_ref_ck"
    ),
)
sa.Index(
    "ix_sku_progress_event_time",
    NewProductSkuProgressEvent_table.c.sku_progress_id,
    NewProductSkuProgressEvent_table.c.recorded_at,
)


class NewProductSkuProgressEvent(Base):
    __table__ = NewProductSkuProgressEvent_table


NewProductSkuProgressMilestone_table = sa.Table(
    "biz_new_product_sku_progress_milestones",
    Base.metadata,
    sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column(
        "sku_progress_id",
        sa.Uuid(),
        sa.ForeignKey("biz_new_product_sku_progress.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("node_type", sa.String(128), nullable=False),
    sa.Column("target_scope", sa.String(24), nullable=False),
    sa.Column("store_id", sa.String(128), nullable=True),
    sa.Column("item_id", sa.String(128), nullable=True),
    sa.Column("purchase_plan_id", sa.Uuid(), nullable=True),
    sa.Column("node_status", sa.String(24), nullable=False),
    sa.Column("event_key", sa.String(255), nullable=False),
    sa.Column("actual_occurred_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column("source_type", sa.String(128), nullable=False),
    sa.Column("source_ref", sa.String(255), nullable=True),
    sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
    sa.Column("confirmed_by", sa.String(255), nullable=True),
    sa.UniqueConstraint("sku_progress_id", "event_key", name="uq_sku_milestone_event"),
    sa.ForeignKeyConstraint(
        ["sku_progress_id", "purchase_plan_id"],
        [
            "biz_new_product_sku_purchase_plans.sku_progress_id",
            "biz_new_product_sku_purchase_plans.id",
        ],
        name="fk_sku_mile_purchase_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "target_scope IN ('sku', 'store', 'listing', 'purchase_plan')", name="sku_mile_scope_ck"
    ),
    sa.CheckConstraint(
        "node_status IN ('confirmed', 'reversed', 'unknown')", name="sku_mile_status_ck"
    ),
    sa.CheckConstraint(
        (
            "(target_scope = 'sku' AND store_id IS NULL AND item_id IS NULL AND "
            "purchase_plan_id IS NULL) OR (target_scope = 'store' AND store_id IS NOT "
            "NULL AND item_id IS NULL AND purchase_plan_id IS NULL) OR (target_scope = "
            "'listing' AND store_id IS NOT NULL AND item_id IS NOT NULL AND "
            "purchase_plan_id IS NULL) OR (target_scope = 'purchase_plan' AND "
            "purchase_plan_id IS NOT NULL AND store_id IS NULL AND item_id IS NULL)"
        ),
        name="sku_mile_scope_identity_ck",
    ),
)
sa.Index(
    "ix_sku_mile_node_time",
    NewProductSkuProgressMilestone_table.c.sku_progress_id,
    NewProductSkuProgressMilestone_table.c.node_type,
    NewProductSkuProgressMilestone_table.c.recorded_at,
)


class NewProductSkuProgressMilestone(Base):
    __table__ = NewProductSkuProgressMilestone_table


WalmartAdSourceObservation_table = sa.Table(
    "dwd_walmart_ad_source_observations",
    Base.metadata,
    sa.Column("observation_key", sa.String(64), primary_key=True, nullable=False),
    sa.Column("source_account_ref", sa.String(128), nullable=True),
    sa.Column("source_interface", sa.String(64), nullable=False),
    sa.Column("business_date_la", sa.Date(), nullable=True),
    sa.Column("source_blob_id", sa.Uuid(), nullable=False),
    sa.Column("source_ordinal", sa.Integer(), nullable=False),
    sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload_json", postgresql.JSONB(), nullable=False),
    sa.CheckConstraint("source_ordinal >= 0", name="ad_source_obs_ordinal_ck"),
    sa.CheckConstraint("last_observed_at >= first_observed_at", name="ad_source_obs_time_ck"),
    sa.CheckConstraint(
        "source_interface IN ('walmart_ad_item_sp_list','walmart_advertiser_list')",
        name="ad_source_obs_interface_ck",
    ),
)
sa.Index(
    "ix_ad_source_obs_scope",
    WalmartAdSourceObservation_table.c.source_account_ref,
    WalmartAdSourceObservation_table.c.business_date_la,
)


class WalmartAdSourceObservation(Base):
    __table__ = WalmartAdSourceObservation_table


SkuProgressCurrent_table = sa.Table(
    "mart_new_product_sku_progress_current",
    Base.metadata,
    sa.Column("source_account_ref", sa.String(128), primary_key=True, nullable=False),
    sa.Column("sku_identity_id", sa.Uuid(), primary_key=True, nullable=False),
    sa.Column("sku", sa.String(255), nullable=False),
    sa.Column("product_name", sa.Text(), nullable=True),
    sa.Column("main_image_url", sa.Text(), nullable=True),
    sa.Column("developer_name", sa.String(255), nullable=True),
    sa.Column("developer_uid", sa.String(255), nullable=True),
    sa.Column("identity_verified", sa.Boolean(), nullable=False),
    sa.Column("development_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("listings_json", postgresql.JSONB(), nullable=False),
    sa.Column("eligible", sa.Boolean(), nullable=False),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
)
sa.Index(
    "ix_sku_progress_mart_scope_date",
    SkuProgressCurrent_table.c.source_account_ref,
    SkuProgressCurrent_table.c.eligible,
    SkuProgressCurrent_table.c.development_at,
)


class SkuProgressCurrent(Base):
    __table__ = SkuProgressCurrent_table
