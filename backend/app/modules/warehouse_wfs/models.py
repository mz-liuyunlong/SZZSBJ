from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
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


class WalmartWfsFeeActualFact(Base):
    __tablename__ = "fact_walmart_wfs_fee_actual"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "source_line_ref"),
        CheckConstraint("actual_fee_amount >= 0", name="actual_fee_nonnegative"),
        CheckConstraint("store_id <> ''", name="store_not_blank"),
        CheckConstraint("item_id <> ''", name="item_not_blank"),
        CheckConstraint("trim(msku) <> ''", name="msku_not_blank"),
        Index(
            "ix_fact_walmart_wfs_fee_actual_identity_date",
            "source_account_ref",
            "business_date_la",
            "store_id",
            "item_id",
            "msku",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str] = mapped_column(Text, nullable=False)
    source_line_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        default="walmart_statement",
        server_default=text("'walmart_statement'"),
        nullable=False,
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WfsFeeAnomalyCase(Base):
    """Formal WFS overcharge case table.

    The table stores case-level workflow state for Walmart WFS fee anomalies. It is
    intentionally independent from Daily Sales / Order Profit recalculation.
    """

    __tablename__ = "ops_wfs_fee_anomaly_cases"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", "item_id", "msku"),
        UniqueConstraint("source_case_ref"),
        CheckConstraint(
            "source_kind in ('legacy_mirror','manual','future_lingxing_profit_order')",
            name="wfs_case_source_kind_allowed",
        ),
        CheckConstraint(
            "status in ('pending_confirm','following','archive_pending','archived','recovered')",
            name="wfs_case_status_allowed",
        ),
        CheckConstraint("priority in ('high','medium','low')", name="wfs_case_priority_allowed"),
        CheckConstraint("severity in ('high','medium','low')", name="wfs_case_severity_allowed"),
        CheckConstraint(
            "archive_review_status in ('none','pending','approved','rejected')",
            name="wfs_case_archive_review_allowed",
        ),
        CheckConstraint("manual_unit_fee >= 0", name="wfs_case_manual_unit_fee_nonnegative"),
        CheckConstraint("actual_unit_fee >= 0", name="wfs_case_actual_unit_fee_nonnegative"),
        CheckConstraint("unit_fee_diff >= 0", name="wfs_case_unit_fee_diff_nonnegative"),
        CheckConstraint("affected_units >= 0", name="wfs_case_affected_units_nonnegative"),
        CheckConstraint(
            "estimated_recover_amount >= 0", name="wfs_case_estimated_recover_nonnegative"
        ),
        CheckConstraint("recovered_amount >= 0", name="wfs_case_recovered_nonnegative"),
        Index("ix_wfs_case_status", "source_account_ref", "status", "next_follow_at"),
        Index("ix_wfs_case_owner", "source_account_ref", "owner_ref", "status"),
        Index(
            "ix_wfs_case_archive_review",
            "source_account_ref",
            "archive_review_status",
            "archive_requested_at",
        ),
        Index("ix_wfs_case_legacy", "legacy_case_id"),
        Index("ix_wfs_case_updated", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    source_kind: Mapped[str] = mapped_column(
        String(32), default="legacy_mirror", server_default=text("'legacy_mirror'"), nullable=False
    )
    source_case_ref: Mapped[str | None] = mapped_column(String(255))
    legacy_case_id: Mapped[int | None]
    legacy_status: Mapped[str | None] = mapped_column(String(32))
    legacy_updated_at: Mapped[datetime | None]
    last_mirrored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_hash: Mapped[str | None] = mapped_column(String(64))

    platform: Mapped[str] = mapped_column(
        String(32), default="walmart", server_default=text("'walmart'"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str] = mapped_column(Text, nullable=False)
    store_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    local_sku_snapshot: Mapped[str | None] = mapped_column(Text)
    product_name_snapshot: Mapped[str | None] = mapped_column(Text)
    owner_ref: Mapped[str | None] = mapped_column(String(128))
    owner_name_snapshot: Mapped[str | None] = mapped_column(String(128))

    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    manual_unit_fee: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    actual_unit_fee: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_fee_diff: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fee_source: Mapped[str] = mapped_column(
        String(64), default="legacy_case", server_default=text("'legacy_case'"), nullable=False
    )
    fee_source_ref: Mapped[str | None] = mapped_column(String(255))
    fee_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculation_version: Mapped[str | None] = mapped_column(String(64))

    affected_units: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    affected_sales_start_date: Mapped[date | None] = mapped_column(Date)
    affected_sales_end_date: Mapped[date | None] = mapped_column(Date)
    affected_units_source: Mapped[str | None] = mapped_column(String(64))
    estimated_recover_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    estimate_formula: Mapped[str | None] = mapped_column(String(128))
    estimate_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    claim_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    recovered_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), default="medium", server_default=text("'medium'"), nullable=False
    )
    severity: Mapped[str] = mapped_column(
        String(16), default="medium", server_default=text("'medium'"), nullable=False
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_by: Mapped[str | None] = mapped_column(String(128))
    first_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)

    case_nos: Mapped[str | None] = mapped_column(Text)
    case_numbers_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    follow_log: Mapped[str | None] = mapped_column(Text)
    latest_follow_note: Mapped[str | None] = mapped_column(Text)
    log_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_at: Mapped[date | None] = mapped_column(Date)
    follow_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    last_follow_by: Mapped[str | None] = mapped_column(String(128))
    last_follow_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    walmart_response_summary: Mapped[str | None] = mapped_column(Text)
    last_rejection_reason: Mapped[str | None] = mapped_column(Text)
    evidence_summary: Mapped[str | None] = mapped_column(Text)

    archive_requested_by: Mapped[str | None] = mapped_column(String(128))
    archive_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_reason_type: Mapped[str | None] = mapped_column(String(64))
    archive_reason: Mapped[str | None] = mapped_column(Text)
    archive_evidence: Mapped[str | None] = mapped_column(Text)
    archive_review_status: Mapped[str] = mapped_column(
        String(32), default="none", server_default=text("'none'"), nullable=False
    )
    archive_reviewed_by: Mapped[str | None] = mapped_column(String(128))
    archive_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_review_note: Mapped[str | None] = mapped_column(Text)

    reason: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str | None] = mapped_column(Text)

    updated_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
