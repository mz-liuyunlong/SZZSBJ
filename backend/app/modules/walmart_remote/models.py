"""Durable Walmart remote collection jobs; never persist tokens or client secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WalmartRemoteJob(Base):
    __tablename__ = "walmart_remote_jobs"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref", "store_id", "request_key", name="uq_walmart_remote_job_key"
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','needs_review')",
            name="ck_walmart_remote_job_status",
        ),
        Index("ix_walmart_remote_job_store", "store_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    operations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    run_id: Mapped[str | None] = mapped_column(String(80))
    files_verified: Mapped[int | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
