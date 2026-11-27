"""PR337 business persistence; raw operational facts remain in existing marts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
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


def utcnow():
    return datetime.now(UTC)


class RuleVersion(Base):
    __tablename__ = "biz_new_product_rule_versions"
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_np_rule_kind_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    applied_by: Mapped[str] = mapped_column(String(128), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MarketScore(Base):
    __tablename__ = "biz_new_product_market_scores"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", "item_id", name="uq_np_market_identity"),
        Index("ix_np_market_updated", "source_account_ref", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class PurchaseApplication(Base):
    __tablename__ = "biz_new_product_purchase_applications"
    __table_args__ = (
        Index("ix_np_purchase_scope_status", "source_account_ref", "status", "created_at"),
        Index("ix_np_purchase_item", "source_account_ref", "store_id", "item_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    request_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    score_rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    applicant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    approved_qty: Mapped[int | None] = mapped_column(Integer)
    approval_request_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TrackingDecision(Base):
    __tablename__ = "biz_new_product_tracking_decisions"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref", "store_id", "item_id", name="uq_np_tracking_identity"
        ),
        Index("ix_np_tracking_status", "source_account_ref", "decision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ActionEvent(Base):
    __tablename__ = "biz_new_product_action_events"
    __table_args__ = (
        Index(
            "ix_np_event_identity_time", "source_account_ref", "store_id", "item_id", "created_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


# The 0088 foundation models are persistence containers; business rules,
# ingestion and workbench approvals are implemented separately after acceptance.
# Do not infer a zero value from a NULL source fact.

MONEY = Numeric(20, 4)
RATIO = Numeric(12, 6)
QTY = Numeric(16, 4)


class NewProductRegistry(Base):
    __tablename__ = "biz_new_product_registry"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref", "store_id", "item_id", name="uq_np_registry_identity"
        ),
        Index("ix_np_registry_store", "source_account_ref", "store_id"),
        Index("ix_np_registry_owner", "source_account_ref", "owner_name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    listing_source_tag: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'小批量测品'")
    )
    is_currently_tagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    image_url: Mapped[str | None] = mapped_column(Text)
    product_name: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(String(128))
    store_name: Mapped[str | None] = mapped_column(String(255))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    category_l1: Mapped[str | None] = mapped_column(Text)
    category_l2: Mapped[str | None] = mapped_column(Text)
    listing_date_la: Mapped[date | None] = mapped_column(Date)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_source_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NewProductPerformanceCurrent(Base):
    __tablename__ = "biz_new_product_performance_current"
    __table_args__ = (Index("ix_np_performance_process", "process_status", "calculated_at"),)
    registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"), primary_key=True
    )
    listing_date_la: Mapped[date | None] = mapped_column(Date)
    first_wfs_available_date_la: Mapped[date | None] = mapped_column(Date)
    first_order_date_la: Mapped[date | None] = mapped_column(Date)
    first_wfs_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_observed_wfs_qty: Mapped[Decimal | None] = mapped_column(QTY)
    first_batch_sold_out_date_la: Mapped[date | None] = mapped_column(Date)
    sold_out_evidence_status: Mapped[str | None] = mapped_column(String(32))
    sold_out_evidence_json: Mapped[dict | None] = mapped_column(JSONB)
    metric_window_start_la: Mapped[date | None] = mapped_column(Date)
    metric_window_end_la: Mapped[date | None] = mapped_column(Date)
    sales_units: Mapped[Decimal | None] = mapped_column(QTY)
    sales_orders: Mapped[int | None] = mapped_column(Integer)
    sales_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_spend_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_clicks: Mapped[int | None] = mapped_column(BigInteger)
    ad_sales_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_spend_ratio_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    acos_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    sample_units: Mapped[Decimal | None] = mapped_column(QTY)
    sample_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    roi: Mapped[Decimal | None] = mapped_column(RATIO)
    profit_margin_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    returned_units: Mapped[Decimal | None] = mapped_column(QTY)
    returned_orders: Mapped[int | None] = mapped_column(Integer)
    return_rate_units_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_rate_orders_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_reasons_json: Mapped[dict | None] = mapped_column(JSONB)
    score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    grade: Mapped[str | None] = mapped_column(String(16))
    process_status: Mapped[str | None] = mapped_column(String(48))
    rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT")
    )
    data_status: Mapped[str | None] = mapped_column(String(32))
    data_coverage_json: Mapped[dict | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NewProductTrackingCurrent(Base):
    __tablename__ = "biz_new_product_tracking_current"
    __table_args__ = (
        Index("ix_np_tracking_current_state", "tracking_status", "calculated_at"),
        Index("ix_np_tracking_current_start", "tracking_started_date_la"),
        CheckConstraint(
            "final_result IS NULL OR final_result IN ('打品成功','打品失败')",
            name="ck_np_tracking_final_result",
        ),
    )
    registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"), primary_key=True
    )
    purchase_application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("biz_new_product_purchase_applications.id", ondelete="RESTRICT")
    )
    initial_grade: Mapped[str | None] = mapped_column(String(16))
    purchase_suggested_qty: Mapped[Decimal | None] = mapped_column(QTY)
    purchase_approved_qty: Mapped[Decimal | None] = mapped_column(QTY)
    purchase_status: Mapped[str | None] = mapped_column(String(48))
    purchase_order_ref: Mapped[str | None] = mapped_column(String(128))
    purchase_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_domestic_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    full_domestic_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    domestic_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_shipments_json: Mapped[dict | None] = mapped_column(JSONB)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    tracking_started_date_la: Mapped[date | None] = mapped_column(Date)
    tracking_start_status: Mapped[str | None] = mapped_column(String(32))
    tracking_start_evidence_json: Mapped[dict | None] = mapped_column(JSONB)
    wfs_available_qty: Mapped[Decimal | None] = mapped_column(QTY)
    wfs_inventory_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cumulative_sales_units: Mapped[Decimal | None] = mapped_column(QTY)
    cumulative_sales_orders: Mapped[int | None] = mapped_column(Integer)
    cumulative_sales_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    cumulative_ad_spend_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    cumulative_ad_clicks: Mapped[int | None] = mapped_column(BigInteger)
    cumulative_profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    cumulative_roi: Mapped[Decimal | None] = mapped_column(RATIO)
    cumulative_profit_margin_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    returned_units: Mapped[Decimal | None] = mapped_column(QTY)
    returned_orders: Mapped[int | None] = mapped_column(Integer)
    return_rate_units_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_rate_orders_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_reasons_json: Mapped[dict | None] = mapped_column(JSONB)
    trend_7d_json: Mapped[dict | None] = mapped_column(JSONB)
    trend_14d_json: Mapped[dict | None] = mapped_column(JSONB)
    trend_30d_json: Mapped[dict | None] = mapped_column(JSONB)
    system_recommendation: Mapped[str | None] = mapped_column(String(48))
    triggered_rules_json: Mapped[dict | None] = mapped_column(JSONB)
    rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT")
    )
    tracking_status: Mapped[str | None] = mapped_column(String(48))
    final_result: Mapped[str | None] = mapped_column(String(24))
    final_result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_review_application_id: Mapped[UUID | None] = mapped_column()
    final_result_snapshot_json: Mapped[dict | None] = mapped_column(JSONB)
    data_status: Mapped[str | None] = mapped_column(String(32))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NewProductDailySnapshot(Base):
    __tablename__ = "biz_new_product_daily_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "registry_id", "phase", "snapshot_date_la", name="uq_np_daily_registry_phase_date"
        ),
        Index("ix_np_daily_phase_date", "phase", "snapshot_date_la"),
        CheckConstraint("phase IN ('performance','tracking')", name="ck_np_daily_phase"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    metric_window_start_la: Mapped[date | None] = mapped_column(Date)
    metric_window_end_la: Mapped[date | None] = mapped_column(Date)
    wfs_available_qty: Mapped[Decimal | None] = mapped_column(QTY)
    sales_units: Mapped[Decimal | None] = mapped_column(QTY)
    sales_orders: Mapped[int | None] = mapped_column(Integer)
    sales_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_spend_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_clicks: Mapped[int | None] = mapped_column(BigInteger)
    ad_spend_ratio_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    sample_units: Mapped[Decimal | None] = mapped_column(QTY)
    sample_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    roi: Mapped[Decimal | None] = mapped_column(RATIO)
    profit_margin_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    returned_units: Mapped[Decimal | None] = mapped_column(QTY)
    returned_orders: Mapped[int | None] = mapped_column(Integer)
    return_rate_units_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_rate_orders_pct: Mapped[Decimal | None] = mapped_column(RATIO)
    return_reasons_json: Mapped[dict | None] = mapped_column(JSONB)
    score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    grade: Mapped[str | None] = mapped_column(String(16))
    metrics_json: Mapped[dict | None] = mapped_column(JSONB)
    triggered_rules_json: Mapped[dict | None] = mapped_column(JSONB)
    rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT")
    )
    data_status: Mapped[str | None] = mapped_column(String(32))
    source_coverage_json: Mapped[dict | None] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NewProductTrackingReviewApplication(Base):
    __tablename__ = "biz_new_product_tracking_review_applications"
    __table_args__ = (
        Index("ix_np_review_state_time", "status", "created_at"),
        Index(
            "uq_np_review_pending",
            "registry_id",
            unique=True,
            postgresql_where=text("status = 'submitted'"),
        ),
        CheckConstraint(
            "proposed_result IN ('打品成功','打品失败')", name="ck_np_review_proposed_result"
        ),
        CheckConstraint(
            "status IN ('submitted','approved','rejected')", name="ck_np_review_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"), nullable=False
    )
    proposed_result: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    applicant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    applicant_reason: Mapped[str] = mapped_column(Text, nullable=False)
    system_recommendation_snapshot: Mapped[str | None] = mapped_column(String(48))
    triggered_rules_snapshot_json: Mapped[dict | None] = mapped_column(JSONB)
    facts_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT")
    )
    approval_request_ref: Mapped[str | None] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NewProductReplenishmentApplication(Base):
    __tablename__ = "biz_new_product_replenishment_applications"
    __table_args__ = (
        Index("ix_np_replenishment_state_time", "status", "created_at"),
        Index("ix_np_replenishment_item_time", "registry_id", "created_at"),
        CheckConstraint("requested_qty > 0", name="ck_np_replenishment_qty"),
        CheckConstraint(
            "status IN ('submitted','approved','rejected')", name="ck_np_replenishment_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"), nullable=False
    )
    requested_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    approved_qty: Mapped[Decimal | None] = mapped_column(QTY)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    applicant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    application_reason: Mapped[str] = mapped_column(Text, nullable=False)
    facts_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    approval_request_ref: Mapped[str | None] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
