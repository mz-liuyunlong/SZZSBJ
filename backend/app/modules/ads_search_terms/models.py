from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
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


def utc_now() -> datetime:
    return datetime.now(UTC)


class WalmartAdSearchTermDailyFact(Base):
    __tablename__ = "fact_walmart_ad_search_term_daily"
    __table_args__ = (
        UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "advertiser_id",
            "source_identity_hash",
            name="uq_walmart_ad_search_term_daily_identity",
        ),
        CheckConstraint("advertiser_id <> ''", name="advertiser_id_not_blank"),
        CheckConstraint("campaign_id <> ''", name="campaign_id_not_blank"),
        CheckConstraint("searched_keyword <> ''", name="searched_keyword_not_blank"),
        CheckConstraint("normalized_search_term <> ''", name="normalized_term_not_blank"),
        CheckConstraint("char_length(source_identity_hash) = 64", name="source_identity_sha256"),
        CheckConstraint("char_length(source_line_hash) = 64", name="source_line_sha256"),
        CheckConstraint("attribution_days IN (3, 14, 30)", name="attribution_days"),
        CheckConstraint(
            "num_ads_shown IS NULL OR num_ads_shown >= 0", name="impressions_nonnegative"
        ),
        CheckConstraint("num_ads_clicks IS NULL OR num_ads_clicks >= 0", name="clicks_nonnegative"),
        CheckConstraint(
            "ad_spend_amount IS NULL OR ad_spend_amount >= 0", name="spend_nonnegative"
        ),
        CheckConstraint(
            "attributed_orders IS NULL OR attributed_orders >= 0", name="orders_nonnegative"
        ),
        Index("ix_walmart_search_term_account_day", "source_account_ref", "business_date_la"),
        Index(
            "ix_walmart_search_term_normalized_day", "normalized_search_term", "business_date_la"
        ),
        Index("ix_walmart_search_term_campaign_day", "campaign_id", "business_date_la"),
        Index(
            "ix_walmart_search_term_listing_day",
            "source_account_ref",
            "store_id",
            "item_id",
            "business_date_la",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text("'America/Los_Angeles'"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    advertiser_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    listing_mapping_status: Mapped[str] = mapped_column(
        String(32),
        default="unresolved",
        server_default=text("'unresolved'"),
        nullable=False,
    )
    mp_seller_name: Mapped[str | None] = mapped_column(Text)
    mp_advertiser_name: Mapped[str | None] = mapped_column(Text)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_name: Mapped[str | None] = mapped_column(Text)
    campaign_type: Mapped[str | None] = mapped_column(String(64))
    campaign_status: Mapped[str | None] = mapped_column(String(64))
    bidding_strategy: Mapped[str | None] = mapped_column(String(64))
    targeting_type: Mapped[str] = mapped_column(String(32), nullable=False)
    searched_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_search_term: Mapped[str] = mapped_column(Text, nullable=False)
    attribution_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default="14"
    )
    num_ads_shown: Mapped[int | None] = mapped_column(Integer)
    num_ads_clicks: Mapped[int | None] = mapped_column(Integer)
    ad_spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_currency_code: Mapped[str | None] = mapped_column(String(3))
    attributed_orders: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    advertised_sku_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    advertised_sku_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    other_sku_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    other_sku_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cvr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cpa: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ad_spend_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    num_ads_shown_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    num_ads_clicks_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    attributed_orders_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    advertised_sku_sales_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    advertised_sku_units_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    other_sku_sales_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    other_sku_units_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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


class WalmartManualKeywordDailyFact(Base):
    __tablename__ = "fact_walmart_keyword_sp_daily"
    __table_args__ = (
        UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "advertiser_id",
            "source_identity_hash",
            name="uq_walmart_keyword_sp_daily_identity",
        ),
        CheckConstraint("advertiser_id <> ''", name="advertiser_id_not_blank"),
        CheckConstraint("campaign_id <> ''", name="campaign_id_not_blank"),
        CheckConstraint("ad_group_id <> ''", name="ad_group_id_not_blank"),
        CheckConstraint("keyword_name <> ''", name="keyword_name_not_blank"),
        CheckConstraint("normalized_keyword <> ''", name="normalized_keyword_not_blank"),
        CheckConstraint("char_length(source_identity_hash) = 64", name="source_identity_sha256"),
        CheckConstraint("char_length(source_line_hash) = 64", name="source_line_sha256"),
        CheckConstraint("attribution_days IN (3, 14, 30)", name="attribution_days"),
        CheckConstraint(
            "num_ads_shown IS NULL OR num_ads_shown >= 0", name="impressions_nonnegative"
        ),
        CheckConstraint("num_ads_clicks IS NULL OR num_ads_clicks >= 0", name="clicks_nonnegative"),
        CheckConstraint(
            "ad_spend_amount IS NULL OR ad_spend_amount >= 0", name="spend_nonnegative"
        ),
        Index("ix_walmart_manual_keyword_account_day", "source_account_ref", "business_date_la"),
        Index("ix_walmart_manual_keyword_normalized_day", "normalized_keyword", "business_date_la"),
        Index(
            "ix_walmart_manual_keyword_campaign_group",
            "advertiser_id",
            "campaign_id",
            "ad_group_id",
        ),
        Index("ix_walmart_manual_keyword_listing", "source_account_ref", "store_id", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Los_Angeles",
        server_default=text("'America/Los_Angeles'"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    advertiser_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    listing_mapping_status: Mapped[str] = mapped_column(
        String(32),
        default="unresolved",
        server_default=text("'unresolved'"),
        nullable=False,
    )
    mp_seller_name: Mapped[str | None] = mapped_column(Text)
    mp_advertiser_name: Mapped[str | None] = mapped_column(Text)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_name: Mapped[str | None] = mapped_column(Text)
    ad_group_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ad_group_name: Mapped[str | None] = mapped_column(Text)
    campaign_status: Mapped[str | None] = mapped_column(String(64))
    ad_group_status: Mapped[str | None] = mapped_column(String(64))
    keyword_id: Mapped[str | None] = mapped_column(String(128))
    keyword_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_status: Mapped[str | None] = mapped_column(String(32))
    keyword_state: Mapped[str | None] = mapped_column(String(32))
    targeting_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attribution_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default="14"
    )
    keyword_bid_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    num_ads_shown: Mapped[int | None] = mapped_column(Integer)
    num_ads_clicks: Mapped[int | None] = mapped_column(Integer)
    ad_spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_spend_currency_code: Mapped[str | None] = mapped_column(String(3))
    attributed_orders: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    advertised_sku_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    other_sku_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cvr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    acos: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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


class AdsSearchTermAction(Base):
    __tablename__ = "ops_ads_search_term_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('add_keyword','add_negative_keyword')", name="action_type"
        ),
        CheckConstraint(
            "status IN ('pending_manual','manually_completed','cancelled')", name="status"
        ),
        CheckConstraint(
            "effect_status IN ('pending','improved','unchanged','declined','insufficient_data')",
            name="effect_status",
        ),
        CheckConstraint("search_term <> ''", name="search_term_not_blank"),
        Index(
            "ix_ads_search_term_actions_account_status",
            "source_account_ref",
            "status",
            "created_at",
        ),
        Index("ix_ads_search_term_actions_term", "normalized_search_term", "created_at"),
        Index("ix_ads_search_term_actions_actor", "created_by", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_fact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fact_walmart_ad_search_term_daily.id", ondelete="SET NULL")
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    search_term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_search_term: Mapped[str] = mapped_column(Text, nullable=False)
    target_scope_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_manual",
        server_default=text("'pending_manual'"),
        nullable=False,
    )
    effect_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, default="", server_default=text("''"), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_by: Mapped[str | None] = mapped_column(String(128))
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    baseline_window_start: Mapped[date | None] = mapped_column(Date)
    baseline_window_end: Mapped[date | None] = mapped_column(Date)
    followup_window_start: Mapped[date | None] = mapped_column(Date)
    followup_window_end: Mapped[date | None] = mapped_column(Date)
    before_metrics_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after_metrics_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AdsSearchTermActionEvent(Base):
    __tablename__ = "ops_ads_search_term_action_events"
    __table_args__ = (
        Index("ix_ads_search_term_action_events_history", "action_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_ads_search_term_actions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    detail_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
