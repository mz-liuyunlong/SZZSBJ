"""Domestic warehouse phase-1 tables.

ODS rows are append-only Lingxing snapshots. The batch board reads only the two DWD
tables: one current receipt line, and its current inventory-batch links.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base

PROVIDER_ID = String(64)
PROVIDER_TIME = String(32)


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomesticOdsMixin:
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
    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DomesticDwdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    @declared_attr
    @classmethod
    def source_run_id(cls) -> Mapped[UUID]:
        return mapped_column(
            ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
        )

    source_ods_id: Mapped[UUID] = mapped_column(nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_update_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LingxingDomesticWarehouseOds(DomesticOdsMixin, Base):
    __tablename__ = "ods_lingxing_domestic_warehouses"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "source_warehouse_id"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        CheckConstraint(
            "char_length(trim(source_warehouse_id)) > 0", name="nonblank_source_warehouse_id"
        ),
    )

    source_warehouse_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    warehouse_name: Mapped[str | None] = mapped_column(String(255))
    warehouse_type: Mapped[str | None] = mapped_column(String(64))
    sub_type: Mapped[str | None] = mapped_column(String(64))


class LingxingDomesticInventoryOds(DomesticOdsMixin, Base):
    __tablename__ = "ods_lingxing_domestic_inventory"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        Index(
            "ix_ods_domestic_inventory_wh_sku",
            "source_account_ref",
            "source_warehouse_id",
            "sku",
        ),
    )

    source_warehouse_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    product_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    seller_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    fnsku: Mapped[str | None] = mapped_column(PROVIDER_ID)
    product_total: Mapped[int | None] = mapped_column(Integer)
    product_valid_num: Mapped[int | None] = mapped_column(Integer)
    product_bad_num: Mapped[int | None] = mapped_column(Integer)
    product_qc_num: Mapped[int | None] = mapped_column(Integer)
    product_lock_num: Mapped[int | None] = mapped_column(Integer)
    good_lock_num: Mapped[int | None] = mapped_column(Integer)
    quantity_receive: Mapped[int | None] = mapped_column(Integer)


class LingxingDomesticBatchOds(DomesticOdsMixin, Base):
    __tablename__ = "ods_lingxing_domestic_batches"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        Index(
            "ix_ods_domestic_batches_ib_sku",
            "source_account_ref",
            "order_sn",
            "sku",
            "store_id",
        ),
    )

    source_warehouse_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    warehouse_name: Mapped[str | None] = mapped_column(String(255))
    batch_no: Mapped[str | None] = mapped_column(PROVIDER_ID)
    source_batch_no: Mapped[str | None] = mapped_column(PROVIDER_ID)
    order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    batch_type: Mapped[int | None] = mapped_column(Integer)
    batch_type_name: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    product_name: Mapped[str | None] = mapped_column(Text)
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_name: Mapped[str | None] = mapped_column(String(255))
    msku: Mapped[str | None] = mapped_column(String(255))
    fnsku: Mapped[str | None] = mapped_column(PROVIDER_ID)
    total_qty: Mapped[int | None] = mapped_column(Integer)
    balance_num: Mapped[int | None] = mapped_column(Integer)
    good_num: Mapped[int | None] = mapped_column(Integer)
    bad_num: Mapped[int | None] = mapped_column(Integer)
    qc_num: Mapped[int | None] = mapped_column(Integer)
    purchase_order_sns: Mapped[str | None] = mapped_column(Text)
    purchase_in_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    batch_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)


class LingxingDomesticInventoryEventOds(DomesticOdsMixin, Base):
    __tablename__ = "ods_lingxing_domestic_inventory_events"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
    )

    statement_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    source_warehouse_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    warehouse_name: Mapped[str | None] = mapped_column(String(255))
    order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    ref_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    seller_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    fnsku: Mapped[str | None] = mapped_column(PROVIDER_ID)
    event_type: Mapped[int | None] = mapped_column(Integer)
    sub_type: Mapped[int | None] = mapped_column(Integer)
    product_good_num: Mapped[int | None] = mapped_column(Integer)
    product_bad_num: Mapped[int | None] = mapped_column(Integer)
    product_qc_num: Mapped[int | None] = mapped_column(Integer)
    opt_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    remark: Mapped[str | None] = mapped_column(Text)


class DwdDomesticReceiptBatch(DomesticDwdMixin, Base):
    """One current receipt line. Arrival date is the Taipei calendar date of receive_time."""

    __tablename__ = "dwd_domestic_receipt_batch"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "receipt_order_sn", "line_ordinal"),
        CheckConstraint("char_length(trim(receipt_order_sn)) > 0", name="nonblank_receipt_order_sn"),
        CheckConstraint("line_ordinal >= 0", name="line_ordinal"),
    )

    receipt_order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    source_warehouse_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    received_qty: Mapped[int | None] = mapped_column(Integer)
    receive_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    received_business_date: Mapped[date | None] = mapped_column(Date)


class DwdDomesticReceiptBatchLink(Base):
    """Current link from a receipt line to an inventory batch. Unmapped rows stay unresolved."""

    __tablename__ = "dwd_domestic_receipt_batch_link"
    __table_args__ = (
        CheckConstraint(
            "mapping_status IN ('unresolved', 'matched')", name="mapping_status"
        ),
        Index("ix_dwd_domestic_receipt_batch_link_batch", "receipt_batch_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    receipt_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_domestic_receipt_batch.id", ondelete="RESTRICT"), nullable=False
    )
    batch_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    batch_no: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    mapped_qty: Mapped[int | None] = mapped_column(Integer)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unresolved")
    mapping_method: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
