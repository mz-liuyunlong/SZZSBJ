from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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


class RawWalmartMonitorEvent(Base):
    """One immutable logical monitor event with all provider attempts."""

    __tablename__ = "raw_walmart_monitor_events"
    __table_args__ = (
        CheckConstraint(
            "schema_version = 'walmart-monitor.raw.v1'",
            name="schema_version_v1",
        ),
        CheckConstraint("target_count BETWEEN 1 AND 100", name="target_count"),
        CheckConstraint("attempt_count BETWEEN 1 AND 20", name="attempt_count"),
        CheckConstraint("raw_hash ~ '^[0-9a-f]{64}$'", name="raw_hash_sha256"),
        CheckConstraint("payload_bytes > 0", name="payload_bytes_positive"),
        Index("ix_raw_walmart_monitor_events_captured_at", "captured_at"),
        Index("ix_raw_walmart_monitor_events_raw_hash", "raw_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    producer_instance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_check_id: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_run_id: Mapped[str | None] = mapped_column(String(128))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    final_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class StandardizedWalmartMonitorListingObservation(Base):
    """Typed, immutable Listing observation parsed from one monitor RAW event."""

    __tablename__ = "std_walmart_monitor_listing_observations"
    __table_args__ = (
        UniqueConstraint(
            "raw_event_id",
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_std_walmart_monitor_observation_event_listing",
        ),
        CheckConstraint(
            "strike_price_amount IS NULL OR strike_price_amount >= 0",
            name="ck_wm_obs_strike_nonneg",
        ),
        CheckConstraint(
            "sale_price_amount IS NULL OR sale_price_amount >= 0",
            name="ck_wm_obs_sale_nonneg",
        ),
        CheckConstraint(
            "average_rating IS NULL OR (average_rating >= 0 AND average_rating <= 5)",
            name="ck_wm_obs_rating_range",
        ),
        CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name="ck_wm_obs_review_nonneg",
        ),
        Index(
            "ix_std_walmart_monitor_observation_listing_captured",
            "source_account_ref",
            "store_id",
            "item_id",
            "captured_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    raw_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_walmart_monitor_events.id", ondelete="CASCADE"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    monitor_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    monitor_source: Mapped[str | None] = mapped_column(String(64))
    monitor_error_code: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(Text)
    strike_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    strike_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    sale_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sale_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    category: Mapped[str | None] = mapped_column(Text)
    source_category_raw: Mapped[str | None] = mapped_column(Text)
    buybox_status: Mapped[str | None] = mapped_column(String(64))
    walmart_seller: Mapped[str | None] = mapped_column(Text)
    is_hijacked: Mapped[bool | None] = mapped_column(Boolean)
    average_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    review_count: Mapped[int | None] = mapped_column(Integer)
    brand: Mapped[str | None] = mapped_column(Text)
    image_urls_json: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class WalmartMonitorListingCurrent(Base):
    """Latest typed monitor observation at the stable Listing business key."""

    __tablename__ = "mart_walmart_monitor_listing_current"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_mart_walmart_monitor_listing_current_identity",
        ),
        Index("ix_mart_walmart_monitor_listing_current_item", "store_id", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_observation_id: Mapped[UUID] = mapped_column(
        ForeignKey("std_walmart_monitor_listing_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_raw_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_walmart_monitor_events.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    monitor_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    monitor_source: Mapped[str | None] = mapped_column(String(64))
    monitor_error_code: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(Text)
    strike_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    strike_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    sale_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sale_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    category: Mapped[str | None] = mapped_column(Text)
    source_category_raw: Mapped[str | None] = mapped_column(Text)
    buybox_status: Mapped[str | None] = mapped_column(String(64))
    walmart_seller: Mapped[str | None] = mapped_column(Text)
    is_hijacked: Mapped[bool | None] = mapped_column(Boolean)
    average_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    review_count: Mapped[int | None] = mapped_column(Integer)
    brand: Mapped[str | None] = mapped_column(Text)
    image_urls_json: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=utc_now,
        nullable=False,
    )
