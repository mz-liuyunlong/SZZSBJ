from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Numeric, String, Text, UniqueConstraint, text
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WfsFeeAnomalyCase(Base):
    __tablename__ = "ops_wfs_fee_anomaly_cases"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "business_date_la", "store_id", "item_id", "msku"),
        CheckConstraint(
            "status in ('未开Case','已开Case','跟进中','已追回','驳回','已关闭')",
            name="status_allowed",
        ),
        CheckConstraint("priority in ('高','中','低')", name="priority_allowed"),
        CheckConstraint("recovered_amount >= 0", name="recovered_nonnegative"),
        Index("ix_ops_wfs_fee_anomaly_cases_status", "source_account_ref", "status", "next_follow_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    msku: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="未开Case", server_default=text("'未开Case'"), nullable=False
    )
    case_no: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(
        String(16), default="中", server_default=text("'中'"), nullable=False
    )
    claim_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    recovered_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    case_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_at: Mapped[date | None] = mapped_column(Date)
    latest_follow: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
