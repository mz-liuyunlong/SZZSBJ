from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, text
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
