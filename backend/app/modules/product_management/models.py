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


def utc_now() -> datetime:
    return datetime.now(UTC)


class ManualProductTag(Base):
    __tablename__ = "manual_product_tags"
    __table_args__ = (UniqueConstraint("tag_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tag_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    deactivated_by: Mapped[str | None] = mapped_column(String(255))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualProductTagAssignment(Base):
    __tablename__ = "manual_product_tag_assignments"
    __table_args__ = (
        UniqueConstraint("product_id", "tag_id", "effective_from"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_period"
        ),
        Index("ix_manual_product_tag_assignments_product_id", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_product_tags.id", ondelete="RESTRICT"), nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ProductPricingRuleVersion(Base):
    __tablename__ = "ref_product_pricing_rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_key", "source_account_ref", "version"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_period"
        ),
        CheckConstraint(
            "storage_month_basis_days > 0 AND pricing_storage_days >= 0",
            name="storage_days",
        ),
        CheckConstraint("other_fixed_cost_cny >= 0", name="other_cost_nonnegative"),
        CheckConstraint("usd_cny_rate IS NULL OR usd_cny_rate > 0", name="fx_positive"),
        CheckConstraint(
            "(fx_date IS NULL AND fx_source IS NULL) OR "
            "(fx_date IS NOT NULL AND fx_source IS NOT NULL)",
            name="fx_pair",
        ),
        CheckConstraint(
            "platform_commission_rate IS NULL OR "
            "(platform_commission_rate >= 0 AND platform_commission_rate < 1)",
            name="commission_rate",
        ),
        CheckConstraint("first_leg_cost_per_kg_cny >= 0", name="first_leg_rate"),
        CheckConstraint(
            "suggested_gross_margin_rate >= minimum_gross_margin_rate AND "
            "minimum_gross_margin_rate >= clearance_gross_margin_rate",
            name="margin_order",
        ),
        CheckConstraint("roi_base IN ('purchase_cost', 'total_cost')", name="roi_base"),
        CheckConstraint(
            "grade_a_min_margin_rate >= grade_b_min_margin_rate AND "
            "grade_a_min_roi >= grade_b_min_roi",
            name="grade_threshold_order",
        ),
        CheckConstraint("rounding_mode = 'none'", name="rounding_mode"),
        Index(
            "ix_ref_product_pricing_rule_versions_active_period",
            "rule_key",
            "source_account_ref",
            "is_active",
            "effective_from",
        ),
        Index(
            "uq_ref_product_pricing_rule_versions_open_active",
            "rule_key",
            "source_account_ref",
            unique=True,
            postgresql_where=text("is_active IS TRUE AND effective_to IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_key: Mapped[str] = mapped_column(
        String(64),
        default="product_management",
        server_default=text("'product_management'"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    wfs_source_url: Mapped[str] = mapped_column(Text, nullable=False)
    wfs_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wfs_confirmed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    wfs_fulfillment_rates_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    wfs_storage_rates_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    identity_wfs_overrides_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    storage_month_basis_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    pricing_storage_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    include_first_leg_fee: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_wfs_fulfillment_fee: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_storage_fee: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    other_fixed_cost_cny: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0"), nullable=False
    )
    usd_cny_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fx_date: Mapped[date | None] = mapped_column(Date)
    fx_source: Mapped[str | None] = mapped_column(String(255))
    platform_commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    first_leg_cost_per_kg_cny: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("12.00"), nullable=False
    )
    suggested_gross_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    minimum_gross_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    clearance_gross_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    roi_base: Mapped[str] = mapped_column(String(32), nullable=False)
    grade_a_min_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    grade_a_min_roi: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    grade_b_min_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    grade_b_min_roi: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    rounding_mode: Mapped[str] = mapped_column(
        String(32), default="none", server_default=text("'none'"), nullable=False
    )
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ProductPricingRecalculationRun(Base):
    __tablename__ = "product_pricing_recalculation_runs"
    __table_args__ = (
        UniqueConstraint(
            "principal_ref",
            "source_account_ref",
            "page_key",
            "capability",
            "mode",
            "idempotency_key",
        ),
        CheckConstraint("char_length(request_digest) = 64", name="request_digest"),
        CheckConstraint(
            "selected_count >= 0 AND matched_count >= 0 AND eligible_count >= 0 AND "
            "affected_count >= 0 AND skipped_count >= 0 AND failed_count >= 0",
            name="counts_nonnegative",
        ),
        CheckConstraint("mode IN ('preview', 'execute')", name="mode"),
        CheckConstraint(
            "status IN ('running', 'previewed', 'succeeded', 'partial', 'no_items', 'failed')",
            name="status",
        ),
        Index(
            "ix_product_pricing_recalculation_runs_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    principal_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    page_key: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pricing_rule_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ref_product_pricing_rule_versions.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductManagementPricingCurrent(Base):
    __tablename__ = "dws_product_management_pricing_current"
    __table_args__ = (
        UniqueConstraint("identity_id"),
        CheckConstraint("char_length(input_hash) = 64", name="input_hash"),
        CheckConstraint(
            "wfs_fulfillment_fee_usd IS NULL OR wfs_fulfillment_fee_usd >= 0",
            name="wfs_fee_usd_nonnegative",
        ),
        CheckConstraint(
            "wfs_fulfillment_fee_cny IS NULL OR wfs_fulfillment_fee_cny >= 0",
            name="wfs_fee_cny_nonnegative",
        ),
        CheckConstraint(
            "estimated_storage_fee_usd IS NULL OR estimated_storage_fee_usd >= 0",
            name="storage_fee_usd_nonnegative",
        ),
        CheckConstraint("price_currency_code = 'USD'", name="price_currency_usd"),
        Index("ix_dws_product_management_pricing_current_product_id", "product_id"),
        Index(
            "ix_dws_product_management_pricing_current_recalculation_key",
            "recalculation_idempotency_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    source_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT")
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ref_product_pricing_rule_versions.id", ondelete="RESTRICT"), nullable=False
    )
    pricing_effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calc_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_status: Mapped[str] = mapped_column(String(64), nullable=False)
    wfs_calc_status: Mapped[str] = mapped_column(String(64), nullable=False)
    wfs_calc_reason: Mapped[str | None] = mapped_column(String(128))
    wfs_fee_source: Mapped[str] = mapped_column(String(64), nullable=False)
    wfs_fulfillment_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    wfs_fulfillment_fee_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    storage_calc_status: Mapped[str] = mapped_column(String(64), nullable=False)
    package_volume_cuft: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    daily_storage_fee_per_unit_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    daily_storage_fee_per_unit_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    estimated_storage_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    estimated_storage_fee_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_leg_calc_status: Mapped[str] = mapped_column(String(64), nullable=False)
    first_leg_fee_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    suggested_target_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    minimum_target_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    clearance_target_margin_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    suggested_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    minimum_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    clearance_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    suggested_gross_margin_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    suggested_roi: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    product_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    grade_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    commission_source: Mapped[str] = mapped_column(String(32), nullable=False)
    pricing_breakdown_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    recalculation_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_pricing_recalculation_runs.id", ondelete="SET NULL")
    )
    recalculation_idempotency_key: Mapped[str | None] = mapped_column(String(255))
    recalculation_reason: Mapped[str | None] = mapped_column(Text)
    recalculated_by: Mapped[str | None] = mapped_column(String(255))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class UserTableView(Base):
    __tablename__ = "user_table_views"
    __table_args__ = (
        UniqueConstraint("principal_ref", "page_key", "view_key"),
        CheckConstraint("schema_version >= 1", name="schema_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    principal_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    page_key: Mapped[str] = mapped_column(String(64), nullable=False)
    view_key: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_column_keys_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    column_widths_json: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
