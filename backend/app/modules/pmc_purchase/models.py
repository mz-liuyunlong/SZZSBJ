"""ODS tables for the PMC purchase board (Gate 2, PR-B).

Layering rule (docs/data-sources/database-layering-standard.md): every row keeps the
complete provider record in ``payload_json`` and is appended, never overwritten; the
extracted columns exist only so the board can filter, sort, aggregate and join without
re-parsing JSON. DWD / DWS layers (Gate 3) derive from these tables; the frontend never
reads them directly.

Provider values are stored as delivered: timestamps stay as the ``Y-m-d H:i:s`` strings
Lingxing returns (Asia/Shanghai, parsed in DWD), identifiers stay strings so large ids
never lose precision, and money uses ``Numeric``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base

PROVIDER_TIME = String(32)
PROVIDER_ID = String(64)
MONEY = Numeric(18, 4)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PmcPurchaseOdsMixin:
    """Governance linkage shared by every purchase ODS row."""

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
    # Position of the header record inside the raw page (``data[]`` / ``data.list[]``).
    source_item_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingPurchasePlanOds(PmcPurchaseOdsMixin, Base):
    """One row per purchase plan (``getPurchasePlans`` ``data[]``)."""

    __tablename__ = "ods_lingxing_purchase_plans"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "plan_sn"),
        CheckConstraint("char_length(trim(plan_sn)) > 0", name="nonblank_plan_sn"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        Index("ix_ods_purchase_plans_plan_sn", "plan_sn"),
    )

    plan_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    status_text: Mapped[str | None] = mapped_column(String(64))
    create_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    expect_arrive_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    sid: Mapped[str | None] = mapped_column(PROVIDER_ID)
    seller_name: Mapped[str | None] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    product_name: Mapped[str | None] = mapped_column(Text)
    quantity_plan: Mapped[int | None] = mapped_column(Integer)
    remark: Mapped[str | None] = mapped_column(Text)
    plan_remark: Mapped[str | None] = mapped_column(Text)
    purchaser_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    purchaser_name: Mapped[str | None] = mapped_column(String(255))
    is_aux: Mapped[int | None] = mapped_column(Integer)
    is_combo: Mapped[int | None] = mapped_column(Integer)
    wid: Mapped[str | None] = mapped_column(PROVIDER_ID)
    warehouse_name: Mapped[str | None] = mapped_column(String(255))
    ppg_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)


class LingxingPurchaseOrderOds(PmcPurchaseOdsMixin, Base):
    """One row per purchase order header (``purchaseOrderList`` ``data[]``)."""

    __tablename__ = "ods_lingxing_purchase_orders"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "order_sn"),
        CheckConstraint("char_length(trim(order_sn)) > 0", name="nonblank_order_sn"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        CheckConstraint("item_count >= 0", name="item_count"),
        Index("ix_ods_purchase_orders_order_sn", "order_sn"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    custom_order_sn: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int | None] = mapped_column(Integer)
    status_shipped: Mapped[int | None] = mapped_column(Integer)
    purchase_type: Mapped[int | None] = mapped_column(Integer)
    order_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    create_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    auditor_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    quantity_total: Mapped[int | None] = mapped_column(Integer)
    quantity_receive: Mapped[int | None] = mapped_column(Integer)
    quantity_real: Mapped[int | None] = mapped_column(Integer)
    amount_total: Mapped[Decimal | None] = mapped_column(MONEY)
    purchase_currency: Mapped[str | None] = mapped_column(String(16))
    purchase_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    shipping_price: Mapped[Decimal | None] = mapped_column(MONEY)
    other_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    purchaser_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    # Number of ``item_list`` entries seen on the header; lets the quality check compare
    # header totals with the detail rows written to ``ods_lingxing_purchase_order_items``.
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


class LingxingPurchaseOrderItemOds(PmcPurchaseOdsMixin, Base):
    """One row per purchase order line (``purchaseOrderList`` ``data[].item_list[]``)."""

    __tablename__ = "ods_lingxing_purchase_order_items"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal", "line_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "order_sn", "item_id"),
        CheckConstraint("char_length(trim(order_sn)) > 0", name="nonblank_order_sn"),
        CheckConstraint("char_length(trim(item_id)) > 0", name="nonblank_item_id"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        CheckConstraint("line_ordinal >= 0", name="line_ordinal"),
        Index("ix_ods_purchase_order_items_order_sn", "order_sn"),
        Index("ix_ods_purchase_order_items_item_id", "item_id"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    # Lingxing ``item_list.id``; receipt lines reference it as ``order_item_id``.
    item_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sid: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    fnsku: Mapped[str | None] = mapped_column(String(64))
    quantity_plan: Mapped[int | None] = mapped_column(Integer)
    quantity_real: Mapped[int | None] = mapped_column(Integer)
    quantity_receive: Mapped[int | None] = mapped_column(Integer)
    quantity_qc: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    quantity_per_case: Mapped[int | None] = mapped_column(Integer)
    cases_num: Mapped[int | None] = mapped_column(Integer)
    expect_arrive_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    wid: Mapped[str | None] = mapped_column(PROVIDER_ID)
    is_delete: Mapped[int | None] = mapped_column(Integer)
    remark: Mapped[str | None] = mapped_column(Text)


class LingxingReceiptOrderOds(PmcPurchaseOdsMixin, Base):
    """One row per receipt order header (``PurchaseReceiptOrder/getOrderList`` ``data.list[]``)."""

    __tablename__ = "ods_lingxing_receipt_orders"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "order_sn"),
        CheckConstraint("char_length(trim(order_sn)) > 0", name="nonblank_order_sn"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        CheckConstraint("item_count >= 0", name="item_count"),
        Index("ix_ods_receipt_orders_business_order_sn", "business_order_sn"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    # Purchase order number the receipt belongs to.
    business_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    status: Mapped[int | None] = mapped_column(Integer)
    order_type: Mapped[int | None] = mapped_column(Integer)
    qc_type: Mapped[int | None] = mapped_column(Integer)
    # Arrival date for the board: purchase lead time ends here.
    receive_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    expect_arrival_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    create_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    update_time: Mapped[str | None] = mapped_column(PROVIDER_TIME)
    wid: Mapped[str | None] = mapped_column(PROVIDER_ID)
    # Domestic-warehouse inbound order numbers (IB...), the seam to the warehouse board.
    inbound_order_sns: Mapped[list[str] | None] = mapped_column(JSONB)
    supplier_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    logistics_company: Mapped[str | None] = mapped_column(String(255))
    logistics_order_no: Mapped[str | None] = mapped_column(String(255))
    shipping_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    shipping_currency: Mapped[str | None] = mapped_column(String(16))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


class LingxingReceiptOrderItemOds(PmcPurchaseOdsMixin, Base):
    """One row per receipt line (``data.list[].item_list[]``)."""

    __tablename__ = "ods_lingxing_receipt_order_items"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal", "line_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "receipt_order_sn", "line_ordinal"),
        CheckConstraint("char_length(trim(receipt_order_sn)) > 0", name="nonblank_receipt_sn"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
        CheckConstraint("line_ordinal >= 0", name="line_ordinal"),
        Index("ix_ods_receipt_order_items_order_item_id", "order_item_id"),
    )

    receipt_order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # Purchase order line id (== ``ods_lingxing_purchase_order_items.item_id``).
    order_item_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    item_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(Text)
    fnsku: Mapped[str | None] = mapped_column(String(64))
    seller_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    notice_num_total: Mapped[int | None] = mapped_column(Integer)
    # Actually received quantity: the numerator for arrival progress.
    product_receive_num: Mapped[int | None] = mapped_column(Integer)
    quantity_qc_prepare: Mapped[int | None] = mapped_column(Integer)
    quantity_qc_already: Mapped[int | None] = mapped_column(Integer)
    quality_examine_status: Mapped[int | None] = mapped_column(Integer)
    qc_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    remark: Mapped[str | None] = mapped_column(Text)


PMC_PURCHASE_ODS_TABLES: tuple[str, ...] = (
    LingxingPurchasePlanOds.__tablename__,
    LingxingPurchaseOrderOds.__tablename__,
    LingxingPurchaseOrderItemOds.__tablename__,
    LingxingReceiptOrderOds.__tablename__,
    LingxingReceiptOrderItemOds.__tablename__,
)
