"""WFS shipment-board tables fed from Lingxing (read-only sync).

ODS rows are append-only snapshots of two Lingxing pages (one row per record per run);
the board reads only the published ``mart_wfs_shipment_board`` version selected in
``gov_wfs_board_publications``.  Nothing here calls Lingxing or Walmart.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base

PROVIDER_ID = String(64)
PROVIDER_TIME = String(32)
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")

PMC_WFS_ODS_TABLES: Final[frozenset[str]] = frozenset(
    {
        "ods_lingxing_wfs_cargos",
        "ods_lingxing_wfs_cargo_goods",
        "ods_lingxing_wfs_shipping_lists",
    }
)

# Lingxing cargo_status integers (official field table) → platform status names.
WFS_CARGO_STATUS: Final[dict[int, str]] = {
    0: "PENDING_SHIPMENT_DETAILS",
    1: "AWAITING_DELIVERY",
    2: "RECEIVING_IN_PROGRESS",
    3: "CLOSED",
    4: "CANCELLED",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class WfsOdsMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    @declared_attr
    @classmethod
    def run_id(cls) -> Mapped[UUID]:
        return mapped_column(
            ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
        )

    @declared_attr
    @classmethod
    def raw_request_ref_id(cls) -> Mapped[UUID]:
        return mapped_column(
            ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"), nullable=False
        )

    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_item_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingWfsCargoOds(WfsOdsMixin, Base):
    """One ``queryWFSCargoPage`` record (cargo header). Goods live in the child table."""

    __tablename__ = "ods_lingxing_wfs_cargos"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "cargo_id"),
        Index("ix_wfs_cargos_code", "source_account_ref", "cargo_code"),
        Index("ix_wfs_cargos_run", "run_id"),
    )

    cargo_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    cargo_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    in_bound_order_id: Mapped[str | None] = mapped_column(String(128))
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_name: Mapped[str | None] = mapped_column(String(255))
    country_name: Mapped[str | None] = mapped_column(String(64))
    creator: Mapped[str | None] = mapped_column(String(128))
    logistics_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    cargo_create_date: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    update_date: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    system_update_date: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    status: Mapped[int | None] = mapped_column(Integer)
    cargo_status: Mapped[str | None] = mapped_column(String(64))
    status_name: Mapped[str | None] = mapped_column(String(64))
    cargo_sync_status: Mapped[str | None] = mapped_column(String(64))
    shipping_list_codes: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    distribution_addresses: Mapped[str | None] = mapped_column(Text)
    return_addresses: Mapped[str | None] = mapped_column(Text)
    to_pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_await_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_receive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    goods_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LingxingWfsCargoGoodsOds(WfsOdsMixin, Base):
    """One ``cargo_good_list[]`` line of a cargo record (declared / shipped / received)."""

    __tablename__ = "ods_lingxing_wfs_cargo_goods"
    __table_args__ = (
        UniqueConstraint("run_id", "source_account_ref", "cargo_id", "line_ordinal"),
        Index("ix_wfs_cargo_goods_cargo", "run_id", "cargo_id"),
    )

    cargo_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    cargo_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    msku: Mapped[str | None] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(String(500))
    gtin: Mapped[str | None] = mapped_column(String(64))
    declare_num: Mapped[int | None] = mapped_column(Integer)
    shipments_num: Mapped[int | None] = mapped_column(Integer)
    received_num: Mapped[int | None] = mapped_column(Integer)
    damaged_qty: Mapped[int | None] = mapped_column(Integer)


class LingxingWfsShippingListOds(WfsOdsMixin, Base):
    """One ``queryShippingListPage`` record (platform-warehouse shipping list / SP order)."""

    __tablename__ = "ods_lingxing_wfs_shipping_lists"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "shipping_code"),
        Index("ix_wfs_shipping_lists_run", "run_id"),
    )

    shipping_code: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    shipping_status: Mapped[str | None] = mapped_column(String(32))
    warehouse_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    logistics_provider_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    logistics_channel_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    logistics_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    creator: Mapped[str | None] = mapped_column(String(128))
    principal_user_name: Mapped[str | None] = mapped_column(String(128))
    gmt_create: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    delivery_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    actual_delivery_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    sail_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    arrival_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    expected_arrival_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    actual_due_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    order_logistics_status: Mapped[str | None] = mapped_column(String(64))
    head_fee_type: Mapped[str | None] = mapped_column(String(64))
    shipping_remark: Mapped[str | None] = mapped_column(Text)
    cargo_codes: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    logistics_numbers: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    tracking_numbers: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    goods_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    box_num_total: Mapped[int | None] = mapped_column(Integer)
    shipments_num_total: Mapped[int | None] = mapped_column(Integer)


class WfsBoardPublication(Base):
    """A published board version built from explicitly selected succeeded runs."""

    __tablename__ = "gov_wfs_board_publications"
    __table_args__ = (
        CheckConstraint("status IN ('published')", name="wfs_board_publication_status"),
        Index(
            "uq_wfs_board_current",
            "source_account_ref",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="published", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cargo_run_id: Mapped[UUID] = mapped_column(nullable=False)
    shipping_run_id: Mapped[UUID | None] = mapped_column()
    coverage_start: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end: Mapped[date] = mapped_column(Date, nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class WfsShipmentBoardRow(Base):
    """One WFS cargo per row in a published version; ``payload_json`` holds the detail."""

    __tablename__ = "mart_wfs_shipment_board"
    __table_args__ = (
        UniqueConstraint("publication_id", "source_account_ref", "cargo_id"),
        Index("ix_wfs_board_status", "publication_id", "status", "cargo_created_at"),
        Index("ix_wfs_board_store", "publication_id", "store_id"),
        Index("ix_wfs_board_code", "publication_id", "cargo_code"),
        Index("ix_wfs_board_inbound", "publication_id", "in_bound_order_id"),
    )

    publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_wfs_board_publications.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    cargo_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    cargo_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    in_bound_order_id: Mapped[str | None] = mapped_column(String(128))
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int | None] = mapped_column(Integer)
    status_name: Mapped[str | None] = mapped_column(String(64))
    cargo_sync_status: Mapped[str | None] = mapped_column(String(64))
    logistics_code: Mapped[str | None] = mapped_column(PROVIDER_ID)
    cargo_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cargo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_await_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_receive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_units: Mapped[int | None] = mapped_column(Integer)
    shipped_units: Mapped[int | None] = mapped_column(Integer)
    received_units: Mapped[int | None] = mapped_column(Integer)
    damaged_units: Mapped[int | None] = mapped_column(Integer)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shipping_codes: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    shipping_status: Mapped[str | None] = mapped_column(String(32))
    warehouse_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date)
    arrival_date: Mapped[date | None] = mapped_column(Date)
    expected_arrival_date: Mapped[date | None] = mapped_column(Date)
    logistics_numbers: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
