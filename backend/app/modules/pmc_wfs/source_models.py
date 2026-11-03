"""File-sourced WFS facts: verified collection files → RAW file registry → ODS rows.

Data source decision ``pmc-wfs-logistics-phase1-decision.md`` D-1 (A): Walmart inbound
facts and the carrier (众壹) track are loaded from files that the approved collectors have
already produced and checksum-verified. Loading never calls Walmart, Lingxing or the
carrier. ``raw_pmc_wfs_source_files`` keeps one row per loaded file (sha256, path, row
count); ODS rows point at their file. Per ``(source, endpoint, scope_key)`` exactly one file
is current; older files stay for audit.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_wfs.lingxing_models import JSON_TYPE, utc_now

SOURCE_WALMART: Final = "walmart"
SOURCE_ZHONGYI: Final = "zhongyi"
SOURCE_LINGXING: Final = "lingxing"
ENDPOINTS: Final[dict[str, frozenset[str]]] = {
    SOURCE_WALMART: frozenset({"inbound_shipments", "inbound_shipment_items", "inventory_log"}),
    SOURCE_ZHONGYI: frozenset({"orders_summary", "orders_track"}),
    SOURCE_LINGXING: frozenset({"logistics_channels"}),
}
SOURCE_FILE_TABLES: Final = (
    "raw_pmc_wfs_source_files",
    "ods_walmart_wfs_inbound_shipments",
    "ods_walmart_wfs_inbound_items",
    "ods_walmart_wfs_receipts",
    "ods_carrier_zhongyi_orders",
    "ods_carrier_zhongyi_tracks",
    "ods_lingxing_logistics_channels",
)


class PmcWfsSourceFile(Base):
    """One verified collection file loaded into ODS (RAW evidence: path + sha256)."""

    __tablename__ = "raw_pmc_wfs_source_files"
    __table_args__ = (
        CheckConstraint(
            "source IN ('walmart', 'zhongyi', 'lingxing')", name="pmc_wfs_source_file_source"
        ),
        UniqueConstraint("source", "endpoint", "scope_key", "sha256"),
        Index(
            "uq_pmc_wfs_source_file_current",
            "source",
            "endpoint",
            "scope_key",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    loaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


def _file_fk() -> Any:
    return mapped_column(
        ForeignKey("raw_pmc_wfs_source_files.id", ondelete="RESTRICT"), nullable=False
    )


class WalmartWfsInboundShipmentOds(Base):
    __tablename__ = "ods_walmart_wfs_inbound_shipments"
    __table_args__ = (
        UniqueConstraint("file_id", "shipment_id"),
        Index("ix_wm_wfs_ship_shipment", "shipment_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_order_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    created_date: Mapped[date | None] = mapped_column(Date)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    shipment_units: Mapped[int | None] = mapped_column(Integer)
    received_units: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class WalmartWfsInboundItemOds(Base):
    __tablename__ = "ods_walmart_wfs_inbound_items"
    __table_args__ = (Index("ix_wm_wfs_item_shipment", "shipment_id", "gtin"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(255))
    item_qty: Mapped[int | None] = mapped_column(Integer)
    received_qty: Mapped[int | None] = mapped_column(Integer)
    damaged_qty: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class WalmartWfsReceiptOds(Base):
    """Walmart inventory-log rows of type ``Receipt`` that carry a shipment id."""

    __tablename__ = "ods_walmart_wfs_receipts"
    __table_args__ = (Index("ix_wm_wfs_receipt_shipment", "shipment_id", "gtin"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    transaction_time: Mapped[str | None] = mapped_column(String(40))
    transaction_date: Mapped[date | None] = mapped_column(Date)
    changed_units: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class CarrierZhongyiOrderOds(Base):
    __tablename__ = "ods_carrier_zhongyi_orders"
    __table_args__ = (
        UniqueConstraint("file_id", "order_number"),
        Index("ix_zy_order_customer", "customer_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_number: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    total_weight_kg: Mapped[str | None] = mapped_column(String(32))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class CarrierZhongyiTrackOds(Base):
    __tablename__ = "ods_carrier_zhongyi_tracks"
    __table_args__ = (Index("ix_zy_track_order", "order_number", "track_time"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    track_time: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class LingxingLogisticsChannelOds(Base):
    __tablename__ = "ods_lingxing_logistics_channels"
    __table_args__ = (UniqueConstraint("file_id", "channel_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = _file_fk()
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255))
    provider_id: Mapped[str | None] = mapped_column(String(64))
    provider_name: Mapped[str | None] = mapped_column(String(255))
    method_name: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[str | None] = mapped_column(String(16))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
