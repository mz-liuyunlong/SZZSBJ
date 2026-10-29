"""Run-scoped Walmart remote business data, isolated from Lingxing-owned facts.

Raw CSV fields are retained as JSONB with searchable identity columns. A run
is committed atomically with its batch receipt, making recovery idempotent.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class WalmartRemoteIngestBatch(Base):
    __tablename__ = "walmart_remote_ingest_batches"
    __table_args__ = (
        UniqueConstraint("store_id", "run_id", name="uq_walmart_remote_ingest_run"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("walmart_remote_jobs.id"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_hashes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    row_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class _RemoteBusinessRow(Base):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(128))
    sku: Mapped[str | None] = mapped_column(String(255))
    gtin: Mapped[str | None] = mapped_column(String(128))
    shipment_id: Mapped[str | None] = mapped_column(String(128))
    event_id: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


def _constraints(table: str) -> tuple[object, ...]:
    return (
        UniqueConstraint("store_id", "run_id", "row_number", name="uq_" + table + "_row"),
        Index("ix_" + table + "_store_date", "source_account_ref", "store_id", "snapshot_date"),
        Index("ix_" + table + "_identity", "store_id", "item_id", "sku"),
    )


class WalmartRemoteWfsInventory(_RemoteBusinessRow):
    __tablename__ = "walmart_remote_wfs_inventory"
    __table_args__ = _constraints(__tablename__)


class WalmartRemoteInboundShipment(_RemoteBusinessRow):
    __tablename__ = "walmart_remote_inbound_shipments"
    __table_args__ = _constraints(__tablename__)


class WalmartRemoteInboundItem(_RemoteBusinessRow):
    __tablename__ = "walmart_remote_inbound_items"
    __table_args__ = _constraints(__tablename__)


class WalmartRemoteInventoryLog(_RemoteBusinessRow):
    __tablename__ = "walmart_remote_inventory_log"
    __table_args__ = _constraints(__tablename__)
