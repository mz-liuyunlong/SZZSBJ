"""Immutable versions of the global Listing grade configuration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingGradeRuleVersion(Base):
    __tablename__ = "biz_listing_grade_rule_versions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)



def utc_now() -> datetime:
    return datetime.now(UTC)


class ListingEvaluationRun(Base):
    """One idempotent diagnostic run per China calendar date."""

    __tablename__ = "biz_listing_evaluation_runs"
    __table_args__ = (
        UniqueConstraint("schedule_date_cn", name="uq_listing_evaluation_run_schedule_date"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "total_listings >= 0 AND processed_listings >= 0 "
            "AND grade_candidate_count >= 0 AND lifecycle_candidate_count >= 0 "
            "AND blocked_count >= 0 AND attempt_count >= 0",
            name="nonnegative_counters",
        ),
        Index("ix_listing_evaluation_runs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    schedule_date_cn: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_listings: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_listings: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    grade_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    lifecycle_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_dispatch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ListingEvaluationSnapshot(Base):
    """Immutable-per-run diagnostic snapshot; never writes the current Listing grade."""

    __tablename__ = "biz_listing_evaluation_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "listing_id", name="uq_listing_evaluation_snapshot_run_listing"),
        CheckConstraint("valid_short >= 0 AND valid_medium >= 0", name="valid_financial_days"),
        CheckConstraint(
            "observed_stock_days_7 >= 0 AND low_stock_days_7 >= 0 "
            "AND valid_stock_days_30 >= 0",
            name="valid_stock_days",
        ),
        Index("ix_listing_evaluation_snapshot_listing_cutoff", "listing_id", "cutoff_date_la"),
        Index("ix_listing_evaluation_snapshot_grade", "cutoff_date_la", "grade_candidate"),
        Index("ix_listing_evaluation_snapshot_scope", "run_id", "source_account_ref"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_listing_evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[UUID] = mapped_column(nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    cutoff_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    current_lifecycle: Mapped[str | None] = mapped_column(String(64))
    current_grade: Mapped[str | None] = mapped_column(String(64))
    lifecycle_candidate: Mapped[str | None] = mapped_column(String(64))
    grade_candidate: Mapped[str | None] = mapped_column(String(64))
    valid_short: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_medium: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    weighted_margin_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    valid_stock_days_30: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    observed_stock_days_7: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    low_stock_days_7: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    prior_effective_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    currently_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rule_source: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    evidence_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    publication_status: Mapped[str] = mapped_column(String(64), nullable=False, default="blocked", server_default="blocked")
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ListingGradeFollowUpTask(Base):
    """Daily C/D follow-up is created only from an explicitly published grade snapshot."""

    __tablename__ = "biz_listing_grade_follow_up_tasks"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_listing_grade_follow_up_snapshot"),
        CheckConstraint("grade IN ('C', 'D')", name="grade_cd_only"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'canceled')",
            name="status",
        ),
        Index("ix_listing_grade_follow_up_owner_status_due", "owner_ref", "status", "due_date_cn"),
        Index("ix_listing_grade_follow_up_scope", "source_account_ref", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("biz_listing_evaluation_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[UUID] = mapped_column(nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str] = mapped_column(String(1), nullable=False)
    cutoff_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    due_date_cn: Mapped[date] = mapped_column(Date, nullable=False)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
