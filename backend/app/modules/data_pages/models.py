from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.business_rules.constants import DEFAULT_STORE_COMMISSION_RATE


def utc_now() -> datetime:
    return datetime.now(UTC)


SOURCE_SYSTEM_DEFAULT = "'lingxing'"
BUSINESS_TZ_DEFAULT = "'America/Los_Angeles'"
CHINA_TZ_DEFAULT = "'Asia/Shanghai'"
ALLOCATION_STATUSES = "'direct', 'needs_owner_decision', 'skipped'"
COST_STATUSES = "'complete', 'partial', 'missing'"


class LingxingStoreDimension(Base):
    __tablename__ = "dim_lingxing_stores"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "platform_code_raw", "store_id"),
        CheckConstraint("store_id <> ''", name="store_id_not_blank"),
        Index("ix_dim_lingxing_stores_platform_store", "platform_code", "store_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_system: Mapped[str] = mapped_column(
        String(32), default="lingxing", server_default=text(SOURCE_SYSTEM_DEFAULT), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_name_raw: Mapped[str | None] = mapped_column(Text)
    platform_code_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_name: Mapped[str | None] = mapped_column(Text)
    sid: Mapped[str | None] = mapped_column(String(128))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    raw_status: Mapped[str | None] = mapped_column(String(64))
    is_sync: Mapped[bool | None] = mapped_column(Boolean)
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartListingDimension(Base):
    __tablename__ = "dim_walmart_listings"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", "item_id"),
        CheckConstraint("item_id <> ''", name="item_id_not_blank"),
        CheckConstraint("store_id <> ''", name="store_id_not_blank"),
        CheckConstraint("price_amount IS NULL OR price_amount >= 0", name="price_nonnegative"),
        CheckConstraint(
            "available_quantity IS NULL OR available_quantity >= 0", name="available_qty"
        ),
        CheckConstraint(
            "wfs_available_quantity IS NULL OR wfs_available_quantity >= 0",
            name="wfs_available_qty",
        ),
        CheckConstraint(
            "business_hash IS NULL OR char_length(business_hash) = 64",
            name="business_hash_sha256",
        ),
        Index("ix_dim_walmart_listings_store_item", "store_id", "item_id"),
        Index("ix_dim_walmart_listings_local_sku", "local_sku"),
        Index("ix_dim_walmart_listings_msku", "msku"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_system: Mapped[str] = mapped_column(
        String(32), default="lingxing", server_default=text(SOURCE_SYSTEM_DEFAULT), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    platform_code_raw: Mapped[str | None] = mapped_column(String(64))
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_name: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    local_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    picture_url: Mapped[str | None] = mapped_column(Text)
    item_url: Mapped[str | None] = mapped_column(Text)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_currency_code: Mapped[str | None] = mapped_column(String(3))
    price_currency_symbol_raw: Mapped[str | None] = mapped_column(String(16))
    listing_start_source_raw: Mapped[str | None] = mapped_column(Text)
    listing_start_source_timezone: Mapped[str | None] = mapped_column(String(64))
    listing_start_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing_end_source_raw: Mapped[str | None] = mapped_column(Text)
    listing_end_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    average_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    review_count: Mapped[int | None] = mapped_column(Integer)
    gtin: Mapped[str | None] = mapped_column(Text)
    upc: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    raw_status: Mapped[str | None] = mapped_column(String(128))
    standard_status: Mapped[str | None] = mapped_column(String(64))
    fulfillment_type: Mapped[str | None] = mapped_column(String(64))
    fulfillment_type_name: Mapped[str | None] = mapped_column(String(128))
    variant_unique_id: Mapped[str | None] = mapped_column(Text)
    business_hash: Mapped[str | None] = mapped_column(String(64))
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartListingInventoryDailyFact(Base):
    __tablename__ = "fact_walmart_listing_inventory_daily"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date_la",
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_fact_walmart_inventory_daily_identity",
        ),
        CheckConstraint(
            "available_quantity IS NULL OR available_quantity >= 0",
            name="ck_fact_walmart_inventory_daily_available_nonnegative",
        ),
        CheckConstraint(
            "wfs_available_quantity IS NULL OR wfs_available_quantity >= 0",
            name="ck_fact_walmart_inventory_daily_wfs_nonnegative",
        ),
        Index(
            "ix_fact_walmart_inventory_daily_account_date",
            "source_account_ref",
            "snapshot_date_la",
        ),
        Index(
            "ix_fact_walmart_inventory_daily_item_date",
            "source_account_ref",
            "store_id",
            "item_id",
            "snapshot_date_la",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    snapshot_date_la: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    store_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    item_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)

    available_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
    )
    wfs_available_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
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


class WalmartAdvertiserDimension(Base):
    __tablename__ = "dim_walmart_advertisers"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "advertiser_id"),
        CheckConstraint("advertiser_id <> ''", name="advertiser_id_not_blank"),
        Index("ix_dim_walmart_advertisers_store", "store_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    advertiser_id: Mapped[str] = mapped_column(String(128), nullable=False)
    advertiser_name: Mapped[str | None] = mapped_column(Text)
    store_id: Mapped[str | None] = mapped_column(String(128))
    platform_code: Mapped[str | None] = mapped_column(String(64))
    raw_status: Mapped[str | None] = mapped_column(String(64))
    standard_status: Mapped[str | None] = mapped_column(String(64))
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class StoreCommissionRuleVersion(Base):
    __tablename__ = "ref_store_commission_rule_versions"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "platform_code", "store_id", "rule_version"),
        CheckConstraint("commission_rate >= 0 AND commission_rate < 1", name="rate_range"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_period"
        ),
        Index(
            "ix_ref_store_commission_active",
            "source_account_ref",
            "platform_code",
            "store_id",
            "is_active",
            "effective_from",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_code: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        default=DEFAULT_STORE_COMMISSION_RATE,
        server_default=text(str(DEFAULT_STORE_COMMISSION_RATE)),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartSalesItemDailyFact(Base):
    __tablename__ = "fact_walmart_sales_item_daily"
    __table_args__ = (
        UniqueConstraint("business_date_la", "source_account_ref", "store_id", "item_id"),
        CheckConstraint(f"allocation_status IN ({ALLOCATION_STATUSES})", name="allocation_status"),
        CheckConstraint("sales_qty IS NULL OR sales_qty >= 0", name="sales_qty_nonnegative"),
        CheckConstraint("order_count IS NULL OR order_count >= 0", name="order_count_nonnegative"),
        CheckConstraint("sales_amount IS NULL OR sales_amount >= 0", name="sales_nonnegative"),
        Index("ix_fact_walmart_sales_store_date", "store_id", "business_date_la"),
        Index("ix_fact_walmart_sales_item_date", "item_id", "business_date_la"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    platform_code_raw: Mapped[str | None] = mapped_column(String(64))
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sid: Mapped[str | None] = mapped_column(String(128))
    store_name: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    product_name: Mapped[str | None] = mapped_column(Text)
    sales_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    order_count: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_currency_code: Mapped[str | None] = mapped_column(String(3))
    source_date_raw: Mapped[str | None] = mapped_column(Text)
    source_group_key: Mapped[str | None] = mapped_column(String(128))
    allocation_status: Mapped[str] = mapped_column(
        String(32), default="direct", server_default=text("'direct'"), nullable=False
    )
    date_collect_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartOrderItemFact(Base):
    __tablename__ = "fact_walmart_order_items"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "source_order_id", "source_line_hash"),
        CheckConstraint("char_length(source_line_hash) = 64", name="source_line_hash_sha256"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("sales_revenue_amount IS NULL OR sales_revenue_amount >= 0", name="sales"),
        CheckConstraint(
            "order_total_amount IS NULL OR order_total_amount >= 0", name="order_total"
        ),
        Index("ix_fact_walmart_order_items_business_date", "business_date_la"),
        Index("ix_fact_walmart_order_items_store_item", "store_id", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    source_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_order_line_id: Mapped[str | None] = mapped_column(String(128))
    source_line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source_purchase_at_raw: Mapped[str | None] = mapped_column(Text)
    source_purchase_timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Shanghai", server_default=text(CHINA_TZ_DEFAULT), nullable=False
    )
    purchase_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_date_la: Mapped[date | None] = mapped_column(Date)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    order_status_raw: Mapped[str | None] = mapped_column(String(64))
    order_sub_status_raw: Mapped[str | None] = mapped_column(String(64))
    flow_node_raw: Mapped[str | None] = mapped_column(String(64))
    sales_revenue_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_revenue_currency_code: Mapped[str | None] = mapped_column(String(3))
    order_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    order_total_currency_code: Mapped[str | None] = mapped_column(String(3))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_currency_code: Mapped[str | None] = mapped_column(String(3))
    is_sample_order: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    sample_rule_version: Mapped[str | None] = mapped_column(String(64))
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartRefundItemFact(Base):
    __tablename__ = "fact_walmart_refund_items"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "source_return_order_id", "source_line_hash"),
        CheckConstraint("char_length(source_line_hash) = 64", name="source_line_hash_sha256"),
        CheckConstraint("return_type_raw = 'REFUND'", name="return_type_refund"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("refund_amount IS NULL OR refund_amount >= 0", name="refund_nonnegative"),
        Index("ix_fact_walmart_refund_items_business_date", "business_date_la"),
        Index("ix_fact_walmart_refund_items_store_item", "store_id", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    source_return_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_return_line_id: Mapped[str | None] = mapped_column(String(128))
    source_line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_order_id: Mapped[str | None] = mapped_column(String(128))
    purchase_order_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    return_type_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    return_type_name: Mapped[str | None] = mapped_column(Text)
    refund_status_raw: Mapped[str | None] = mapped_column(String(64))
    refund_status_standard: Mapped[str | None] = mapped_column(String(64))
    return_order_date_raw: Mapped[str | None] = mapped_column(Text)
    refund_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_date_la: Mapped[date | None] = mapped_column(Date)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    status_time_raw: Mapped[str | None] = mapped_column(Text)
    status_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_currency_code: Mapped[str | None] = mapped_column(String(3))
    tracking_no: Mapped[str | None] = mapped_column(Text)
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WalmartAdItemSpDailyFact(Base):
    __tablename__ = "fact_walmart_ad_item_sp_daily"
    __table_args__ = (
        UniqueConstraint(
            "business_date_la", "source_account_ref", "advertiser_id", "source_line_hash"
        ),
        CheckConstraint("char_length(source_line_hash) = 64", name="source_line_hash_sha256"),
        CheckConstraint("ad_spend_amount IS NULL OR ad_spend_amount >= 0", name="ad_spend"),
        CheckConstraint("num_ads_clicks IS NULL OR num_ads_clicks >= 0", name="clicks"),
        CheckConstraint("num_ads_shown IS NULL OR num_ads_shown >= 0", name="impressions"),
        Index("ix_fact_walmart_ads_item_date", "item_id", "business_date_la"),
        Index("ix_fact_walmart_ads_advertiser_date", "advertiser_id", "business_date_la"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    advertiser_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(Text)
    campaign_id: Mapped[str | None] = mapped_column(String(128))
    ad_group_id: Mapped[str | None] = mapped_column(String(128))
    ad_item_id: Mapped[str | None] = mapped_column(String(128))
    source_line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str | None] = mapped_column(Text)
    ad_spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_currency_code: Mapped[str | None] = mapped_column(String(3))
    attributed_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    attributed_sales_currency_code: Mapped[str | None] = mapped_column(String(3))
    attributed_orders: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    attributed_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    advertised_sku_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    advertised_sku_sales_currency_code: Mapped[str | None] = mapped_column(String(3))
    advertised_sku_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    num_ads_clicks: Mapped[int | None] = mapped_column(Integer)
    num_ads_shown: Mapped[int | None] = mapped_column(Integer)
    acos: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cvr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class DailySalesItemDayMart(Base):
    __tablename__ = "mart_daily_sales_item_day"
    __table_args__ = (
        UniqueConstraint("business_date_la", "source_account_ref", "store_id", "item_id", "msku"),
        CheckConstraint(f"cost_status IN ({COST_STATUSES})", name="cost_status"),
        CheckConstraint("sales_qty >= 0 AND order_count >= 0", name="nonnegative_counts"),
        CheckConstraint("gross_margin IS NULL OR gross_margin > -10", name="gross_margin_floor"),
        Index("ix_mart_daily_sales_store_date", "store_id", "business_date_la"),
        Index("ix_mart_daily_sales_item_date", "item_id", "business_date_la"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_name: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    local_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    picture_url: Mapped[str | None] = mapped_column(Text)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    sales_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    order_count: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_currency_code: Mapped[str | None] = mapped_column(String(3))
    gross_sales_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    gross_order_count: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    gross_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sample_order_count: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sample_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    cost_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sample_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount_excluding_sample: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    return_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_currency_code: Mapped[str | None] = mapped_column(String(3))
    return_rate_30d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ad_spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_currency_code: Mapped[str | None] = mapped_column(String(3))
    ad_ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    wfs_available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_unit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_currency_code: Mapped[str | None] = mapped_column(String(3))
    wfs_fee_expected_unit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_expected_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_actual_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_variance_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_variance_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    wfs_fee_source: Mapped[str | None] = mapped_column(String(64))
    purchase_cost_unit_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_estimated_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_actual_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_source: Mapped[str | None] = mapped_column(String(64))
    first_leg_cost_unit_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_cost_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_cost_estimated_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_cost_actual_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_cost_source: Mapped[str | None] = mapped_column(String(64))
    storage_fee_unit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_fee_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_fee_currency_code: Mapped[str | None] = mapped_column(String(3))
    storage_fee_estimated_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_fee_actual_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_fee_source: Mapped[str | None] = mapped_column(String(64))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fx_date: Mapped[date | None] = mapped_column(Date)
    fx_source: Mapped[str | None] = mapped_column(String(255))
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    commission_rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ref_store_commission_rule_versions.id", ondelete="SET NULL")
    )
    commission_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    commission_fee_currency_code: Mapped[str | None] = mapped_column(String(3))
    commission_source: Mapped[str | None] = mapped_column(String(64))
    gross_profit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_profit_currency_code: Mapped[str | None] = mapped_column(String(3))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roi: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cost_status: Mapped[str] = mapped_column(
        String(32), default="missing", server_default=text("'missing'"), nullable=False
    )
    missing_cost_codes_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    calculation_warnings_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    sales_7d_trend_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    source_lineage_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    calc_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OrderProfitSkuDayMart(Base):
    __tablename__ = "mart_order_profit_sku_day"
    __table_args__ = (
        UniqueConstraint("business_date_la", "source_account_ref", "local_sku"),
        CheckConstraint(f"cost_status IN ({COST_STATUSES})", name="cost_status"),
        CheckConstraint("store_count >= 0 AND item_count >= 0", name="nonnegative_counts"),
        Index("ix_mart_order_profit_sku_date", "local_sku", "business_date_la"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text(BUSINESS_TZ_DEFAULT),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    local_sku: Mapped[str] = mapped_column(Text, nullable=False)
    item_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    store_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    store_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    order_count: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_currency_code: Mapped[str | None] = mapped_column(String(3))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    commission_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_cost_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_fee_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_profit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_profit_currency_code: Mapped[str | None] = mapped_column(String(3))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roi: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cost_status: Mapped[str] = mapped_column(
        String(32), default="missing", server_default=text("'missing'"), nullable=False
    )
    missing_cost_codes_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    source_lineage_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    calc_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ListingManagementCurrentMart(Base):
    __tablename__ = "mart_listing_management_current"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", "item_id"),
        CheckConstraint("sales_7d >= 0 AND sales_14d >= 0 AND sales_30d >= 0", name="sales"),
        CheckConstraint("ad_spend_30d_amount IS NULL OR ad_spend_30d_amount >= 0", name="ad_spend"),
        Index("ix_mart_listing_current_store_item", "store_id", "item_id"),
        Index("ix_mart_listing_current_local_sku", "local_sku"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_name: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    local_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    picture_url: Mapped[str | None] = mapped_column(Text)
    item_url: Mapped[str | None] = mapped_column(Text)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    product_grade: Mapped[str | None] = mapped_column(String(64))
    tags_json: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    strike_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    strike_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    sale_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sale_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    listing_status: Mapped[str | None] = mapped_column(String(64))
    lifecycle_status: Mapped[str | None] = mapped_column(String(64))
    listing_start_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str | None] = mapped_column(Text)
    wfs_available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inbound_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_7d: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_14d: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    sales_30d: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    ad_spend_30d_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_currency_code: Mapped[str | None] = mapped_column(String(3))
    buybox_status: Mapped[str | None] = mapped_column(String(64))
    walmart_seller: Mapped[str | None] = mapped_column(Text)
    is_hijacked: Mapped[bool | None] = mapped_column(Boolean)
    average_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    review_count: Mapped[int | None] = mapped_column(Integer)
    brand: Mapped[str | None] = mapped_column(Text)
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    wfs_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fee_currency_code: Mapped[str | None] = mapped_column(String(3))
    gtin: Mapped[str | None] = mapped_column(Text)
    upc: Mapped[str | None] = mapped_column(Text)
    gpt_analysis_links_json: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    source_lineage_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ProductCustomTag(Base):
    __tablename__ = "product_custom_tags"
    __table_args__ = (
        CheckConstraint("name <> ''", name="product_custom_tag_name_not_blank"),
        CheckConstraint("color <> ''", name="product_custom_tag_color_not_blank"),
        Index("ix_product_custom_tags_active_sort", "is_active", "sort_order", "name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(16), nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductCustomTagAssignment(Base):
    __tablename__ = "product_custom_tag_assignments"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "item_id",
            "tag_id",
            name="uq_product_custom_tag_assignment_item_tag",
        ),
        CheckConstraint("source_account_ref <> ''", name="tag_assignment_account_not_blank"),
        CheckConstraint("item_id <> ''", name="tag_assignment_item_not_blank"),
        Index("ix_product_custom_tag_assignments_item", "source_account_ref", "item_id"),
        Index("ix_product_custom_tag_assignments_tag", "tag_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_custom_tags.id", ondelete="CASCADE"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
