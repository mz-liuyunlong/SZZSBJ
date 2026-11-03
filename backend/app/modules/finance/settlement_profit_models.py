"""Settlement profit V2 storage (PRP finance-settlement-profit-v2 §6.2, PR-1).

Layering: RAW (existing ods_api_raw_*) -> ODS -> FACT -> MART.  manual_* tables only
override calculation results and never write RAW / ODS / FACT.  cfg_* holds finance
settings.  This module only declares storage; sync handlers (PR-2), the calculation
(PR-3) and the API (PR-4) are delivered in later PRs.

Conventions (PRP §6.2):
- money: numeric(18,4) with an explicit currency or a currency-suffixed column name;
- external ids (order no, GTIN, item id, store id, serial no, report id): strings;
- bill_month / month columns: first day of the month (CHECK day = 1);
- every FACT / MART row carries calc_version so results are reproducible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
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

MONEY = Numeric(18, 4)
FX_RATE = Numeric(18, 8)
RATIO = Numeric(12, 8)

FX_STATUSES = ("final", "missing")
REVIEW_STATUSES = ("pending", "auto", "adjusted", "first_passed", "final_passed", "rejected")
REVIEW_ROW_KINDS = ("order", "unassigned", "reconcile_diff")
INVENTORY_CATEGORIES = ("loss", "non_loss", "claim", "unclassified", "lx_adjust", "unknown")
UNASSIGNED_STATUSES = ("pending", "assigned", "void")
RECONCILE_STATUSES = ("ok", "reconcile_failed", "unassigned_pending")
ADJUSTMENT_KINDS = ("cost", "amount", "assign_item", "note")
ADJUSTMENT_STATUSES = ("active", "revoked")
REVIEW_STAGES = ("first", "final")
REVIEW_DECISIONS = ("pass", "reject")
MONTH_CLOSE_STATUSES = ("closed", "reopened")
POST_CLOSE_DIFF_STATUSES = ("open", "acknowledged", "resolved_by_reopen")
STORE_MAPPING_STATUSES = ("mapped", "unmapped")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _first_of_month(column: str) -> str:
    return f"EXTRACT(DAY FROM {column}) = 1"


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class _OdsSource(_Timestamps):
    """Common ODS lineage: every ODS row points back to its RAW request ref and run."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    source_run_id: Mapped[UUID | None] = mapped_column()
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_row: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )


# --------------------------------------------------------------------------- ODS


class LingxingMpProfitOrderLine(_OdsSource, Base):
    """领星多平台结算利润-订单 /basicOpen/multiplatform/profit/report/order (all fields)."""

    __tablename__ = "ods_lingxing_mp_profit_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "platform_order_no",
            "order_item_no",
            "transaction_type",
            "settlement_date",
            "source_row_seq",
            name="uq_ods_lx_mp_profit_order_identity",
        ),
        CheckConstraint("platform_order_no <> ''", name="lx_profit_order_no_not_blank"),
        Index("ix_ods_lx_mp_profit_order_lookup", "store_id", "platform_order_no", "gtin"),
    )

    platform_order_no: Mapped[str] = mapped_column(String(255), nullable=False)
    order_item_no: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_id: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal | None] = mapped_column(MONEY)
    sales_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    promotion_fee_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    review_accelerator_fee_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )


class WalmartWfsFeeDetailLine(_OdsSource, Base):
    """Walmart WFS 费用明细报表 (by GTIN), collected only via walmart_remote_jobs."""

    __tablename__ = "ods_walmart_wfs_fee_detail_lines"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "report_id",
            "line_no",
            name="uq_ods_wm_wfs_fee_detail_identity",
        ),
        CheckConstraint("report_id <> ''", name="wm_fee_detail_report_not_blank"),
        Index("ix_ods_wm_wfs_fee_detail_gtin_date", "store_id", "gtin", "transaction_date_la"),
    )

    report_id: Mapped[str] = mapped_column(String(255), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    report_period_start: Mapped[date | None] = mapped_column(Date)
    report_period_end: Mapped[date | None] = mapped_column(Date)
    transaction_date_la: Mapped[date | None] = mapped_column(Date)
    fee_type: Mapped[str] = mapped_column(String(128), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[Decimal | None] = mapped_column(MONEY)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    # walmart_remote_jobs.id (one store, one server); kept as a plain reference column.
    remote_job_id: Mapped[UUID | None] = mapped_column()


class WalmartStorageFeeLine(_OdsSource, Base):
    """Walmart 仓储费报表: per-GTIN share of the settlement StorageFee line."""

    __tablename__ = "ods_walmart_storage_fee_lines"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "report_period_start",
            "report_period_end",
            "gtin",
            name="uq_ods_wm_storage_fee_identity",
        ),
        CheckConstraint(
            "report_period_end >= report_period_start", name="wm_storage_fee_period_order"
        ),
        CheckConstraint("gtin <> ''", name="wm_storage_fee_gtin_not_blank"),
    )

    report_id: Mapped[str | None] = mapped_column(String(255))
    report_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    report_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    gtin: Mapped[str] = mapped_column(String(64), nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(128))
    on_hand_quantity: Mapped[Decimal | None] = mapped_column(MONEY)
    volume_cubic_feet: Mapped[Decimal | None] = mapped_column(MONEY)
    storage_fee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    # walmart_remote_jobs.id (one store, one server); kept as a plain reference column.
    remote_job_id: Mapped[UUID | None] = mapped_column()


class WalmartReviewAcceleratorSnapshot(_OdsSource, Base):
    """Walmart /v3/growth/reviews-accelerator/items snapshot, one per settlement period."""

    __tablename__ = "ods_walmart_review_accelerator_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "snapshot_report_key",
            "item_id",
            name="uq_ods_wm_review_accel_identity",
        ),
        CheckConstraint("snapshot_report_key <> ''", name="wm_review_accel_key_not_blank"),
        CheckConstraint("item_id <> ''", name="wm_review_accel_item_not_blank"),
        CheckConstraint("reviews_collected >= 0", name="wm_review_accel_reviews_nonneg"),
    )

    snapshot_report_key: Mapped[str] = mapped_column(String(255), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    enrollment_status: Mapped[str | None] = mapped_column(String(64))
    reviews_collected: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    price_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str] = mapped_column(
        String(3), default="USD", server_default=text("'USD'"), nullable=False
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # walmart_remote_jobs.id (one store, one server); kept as a plain reference column.
    remote_job_id: Mapped[UUID | None] = mapped_column()


# -------------------------------------------------------------------------- FACT


class _FxColumns:
    fx_rate: Mapped[Decimal | None] = mapped_column(FX_RATE)
    fx_month: Mapped[date | None] = mapped_column(Date)
    fx_status: Mapped[str] = mapped_column(
        String(16), default="missing", server_default=text("'missing'"), nullable=False
    )


class _SettlementAmounts:
    """Order / item level settlement columns (USD unless suffixed _cny).

    promotion_fee_usd and packaging_fee_usd are reserved (PRP §0.3): kept NULL and not
    used in any calculation in this PRP.
    """

    sales_amount_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    platform_subsidy_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    refund_amount_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    commission_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    wfs_fulfillment_fee_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    return_fee_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    tax_withheld_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    wfs_service_fee_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    storage_fee_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    inbound_wpc_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    ad_cost_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    review_accelerator_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    disposal_loss_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    promotion_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    packaging_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    purchase_cost_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    head_cost_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    goods_cost_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    gross_profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    gross_profit_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    net_profit_share_cny: Mapped[Decimal | None] = mapped_column(MONEY)


class SettlementOrderLine(_SettlementAmounts, _FxColumns, _Timestamps, Base):
    """账单月 × 店铺 × 订单行 × 商品 calculation result (PRP §8.3–§8.5).

    line_key is the stable business key (store + reportKey + order no + order line no +
    GTIN); manual_* tables reference it instead of the row UUID.  All transaction types of
    one order line within one settlement period are aggregated into one row, so the only
    unique key is (store_id, bill_month, calc_version, line_key); the order number columns
    are a plain index (a sale in period 1 and its refund in period 2 are separate rows).
    """

    __tablename__ = "fact_settlement_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "bill_month",
            "calc_version",
            "line_key",
            name="uq_fact_settlement_order_lines_line_key_version",
        ),
        CheckConstraint(_first_of_month("bill_month"), name="settle_line_bill_month_first_day"),
        CheckConstraint("line_key <> ''", name="settle_line_key_not_blank"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="settle_line_fx_status"),
        CheckConstraint(_in("review_status", REVIEW_STATUSES), name="settle_line_review_status"),
        CheckConstraint("calc_version >= 1", name="settle_line_calc_version_positive"),
        Index("ix_fact_settlement_order_lines_line_key", "line_key"),
        Index(
            "ix_fact_settlement_order_lines_order",
            "store_id",
            "bill_month",
            "platform_order_no",
            "order_item_no",
        ),
        Index("ix_fact_settlement_order_lines_item_month", "store_id", "item_id", "bill_month"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    report_key: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_order_no: Mapped[str] = mapped_column(String(255), nullable=False)
    order_item_no: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    msku: Mapped[str | None] = mapped_column(Text)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_match_status: Mapped[str | None] = mapped_column(String(32))
    review_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'"), nullable=False
    )
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_run_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frozen_by: Mapped[str | None] = mapped_column(String(255))


class InventoryMovementLine(_FxColumns, _Timestamps, Base):
    """库存异动, derived from the inventory-claim PRP's ``ods_lingxing_wfs_cost_valuation_flow``.

    Only rows with ``is_current = true`` are read.  Lingxing serial numbers repeat and can
    change, so they are informational only: a row is identified by the source flow row id
    within one calc_version.  The store comes from the store_code mapping; a row whose
    store_code is not mapped keeps store_id NULL (store_mapping_status = 'unmapped').
    No foreign key to the flow table: it is owned and migrated by the inventory-claim PRP.
    """

    __tablename__ = "fact_inventory_movement_lines"
    __table_args__ = (
        UniqueConstraint(
            "source_flow_id",
            "calc_version",
            name="uq_fact_inventory_movement_lines_flow_version",
        ),
        CheckConstraint(_first_of_month("movement_month"), name="inv_move_month_first_day"),
        CheckConstraint(_in("category", INVENTORY_CATEGORIES), name="inv_move_category"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="inv_move_fx_status"),
        CheckConstraint(
            _in("store_mapping_status", STORE_MAPPING_STATUSES), name="inv_move_store_mapping"
        ),
        CheckConstraint(
            "(store_mapping_status = 'mapped') = (store_id IS NOT NULL)",
            name="inv_move_store_id_matches_mapping",
        ),
        Index("ix_fact_inventory_movement_lines_month", "store_id", "movement_month", "category"),
        Index("ix_fact_inventory_movement_lines_serial", "serial_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # ods_lingxing_wfs_cost_valuation_flow.id (is_current = true at calculation time)
    source_flow_id: Mapped[UUID] = mapped_column(nullable=False)
    source_sync_batch_id: Mapped[UUID | None] = mapped_column()
    store_code: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    store_mapping_status: Mapped[str] = mapped_column(String(16), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(128))
    business_type: Mapped[str] = mapped_column(String(64), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(String(128))
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    movement_month: Mapped[date] = mapped_column(Date, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    goods_value_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    goods_value_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    disposal_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    destination: Mapped[str | None] = mapped_column(String(255))
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SettlementUnassignedAmount(_Timestamps, Base):
    """「待指定」金额 (PRP §8.4): replaces the old shop-level / sporadic buckets."""

    __tablename__ = "fact_settlement_unassigned_amounts"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "bill_month",
            "source_kind",
            "source_ref",
            name="uq_fact_settlement_unassigned_amounts_identity",
        ),
        CheckConstraint(_first_of_month("bill_month"), name="unassigned_bill_month_first_day"),
        CheckConstraint(_in("status", UNASSIGNED_STATUSES), name="unassigned_status"),
        CheckConstraint(
            "status <> 'assigned' OR assigned_item_id IS NOT NULL",
            name="unassigned_assigned_has_item",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'"), nullable=False
    )
    assigned_item_id: Mapped[str | None] = mapped_column(String(128))
    adjustment_id: Mapped[UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SettlementPostCloseDiff(_Timestamps, Base):
    """结账后源数据变化: recorded only, frozen numbers are never changed."""

    __tablename__ = "fact_settlement_post_close_diffs"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "bill_month",
            "line_key",
            "detected_at",
            name="uq_fact_settlement_post_close_diffs_identity",
        ),
        CheckConstraint(_first_of_month("bill_month"), name="post_close_bill_month_first_day"),
        CheckConstraint(_in("status", POST_CLOSE_DIFF_STATUSES), name="post_close_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    old_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    new_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    diff_amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(
        String(24), default="open", server_default=text("'open'"), nullable=False
    )
    frozen_calc_version: Mapped[int] = mapped_column(Integer, nullable=False)


# -------------------------------------------------------------------------- MART


class SettlementProfitItemMonth(_SettlementAmounts, _FxColumns, _Timestamps, Base):
    __tablename__ = "mart_settlement_profit_item_month"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_profit_item_month_key"
        ),
        CheckConstraint(_first_of_month("bill_month"), name="profit_item_month_first_day"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="profit_item_month_fx_status"),
        Index("ix_mart_settlement_profit_item_month_owner", "bill_month", "owner_ref"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    msku: Mapped[str | None] = mapped_column(Text)
    sales_quantity: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    net_profit_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    gross_margin_ratio: Mapped[Decimal | None] = mapped_column(RATIO)
    ad_scope_note: Mapped[str | None] = mapped_column(String(64))
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SettlementOrderReview(_Timestamps, Base):
    """订单审核清单: order rows plus 待指定 / 对平差额 to-do rows (row_kind).

    line_key: order rows reuse the order line key; 待指定 rows use
    store + bill month + source_kind + source_ref; 对平差额 rows use
    store + bill month + "reconcile_diff" (PRP §8.9).
    """

    __tablename__ = "mart_settlement_order_review"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "bill_month", "line_key", name="uq_mart_settlement_order_review_key"
        ),
        CheckConstraint(_first_of_month("bill_month"), name="order_review_month_first_day"),
        CheckConstraint(_in("row_kind", REVIEW_ROW_KINDS), name="order_review_row_kind"),
        CheckConstraint(_in("status", REVIEW_STATUSES), name="order_review_status"),
        CheckConstraint(
            "row_kind <> 'order' OR (platform_order_no IS NOT NULL AND order_item_no IS NOT NULL)",
            name="order_review_order_identity",
        ),
        Index("ix_mart_settlement_order_review_status", "bill_month", "status"),
        Index(
            "ix_mart_settlement_order_review_order",
            "store_id",
            "bill_month",
            "platform_order_no",
            "order_item_no",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    row_kind: Mapped[str] = mapped_column(
        String(16), default="order", server_default=text("'order'"), nullable=False
    )
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    platform_order_no: Mapped[str | None] = mapped_column(String(255))
    order_item_no: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'"), nullable=False
    )
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    first_reviewed_by: Mapped[str | None] = mapped_column(String(255))
    first_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_reviewed_by: Mapped[str | None] = mapped_column(String(255))
    final_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SettlementReconcileStoreMonth(_Timestamps, Base):
    """店铺月对平 (PRP §8.8): |diff| <= 0.01 USD is ok."""

    __tablename__ = "mart_settlement_reconcile_store_month"
    __table_args__ = (
        UniqueConstraint("store_id", "bill_month", name="uq_mart_settlement_reconcile_key"),
        CheckConstraint(_first_of_month("bill_month"), name="reconcile_month_first_day"),
        CheckConstraint(_in("status", RECONCILE_STATUSES), name="reconcile_status"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="reconcile_fx_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_total_usd: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    order_level_total_usd: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unassigned_pending_usd: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    diff_usd: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    ad_daily_vs_settlement_diff_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    cross_month_disposal_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    fx_status: Mapped[str] = mapped_column(
        String(16), default="missing", server_default=text("'missing'"), nullable=False
    )
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryMovementMonth(_Timestamps, Base):
    __tablename__ = "mart_inventory_movement_month"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "item_id", "month", "category", name="uq_mart_inventory_movement_key"
        ),
        CheckConstraint(_first_of_month("month"), name="inv_month_first_day"),
        CheckConstraint(_in("category", INVENTORY_CATEGORIES), name="inv_month_category"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0"), server_default=text("0"), nullable=False
    )
    goods_value_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    goods_value_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    disposal_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)


# ------------------------------------------------------------------------ MANUAL


class _ManualAudit:
    """Audit columns required on every write (PRP §5)."""

    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SettlementOrderAdjustment(_ManualAudit, _Timestamps, Base):
    __tablename__ = "manual_settlement_order_adjustments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_manual_settlement_adjustments_idem"),
        CheckConstraint(_first_of_month("bill_month"), name="adjustment_month_first_day"),
        CheckConstraint(_in("kind", ADJUSTMENT_KINDS), name="adjustment_kind"),
        CheckConstraint(_in("status", ADJUSTMENT_STATUSES), name="adjustment_status"),
        CheckConstraint("reason <> ''", name="adjustment_reason_required"),
        CheckConstraint(
            "status <> 'revoked' OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)",
            name="adjustment_revoked_audit",
        ),
        Index("ix_manual_settlement_adjustments_line", "line_key", "status"),
        Index("ix_manual_settlement_adjustments_month", "store_id", "bill_month"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default=text("'active'"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    revoked_by: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class SettlementReviewAction(_ManualAudit, _Timestamps, Base):
    __tablename__ = "manual_settlement_review_actions"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", "line_key", name="uq_manual_settlement_review_idem_line"
        ),
        CheckConstraint(_first_of_month("bill_month"), name="review_month_first_day"),
        CheckConstraint(_in("stage", REVIEW_STAGES), name="review_stage"),
        CheckConstraint(_in("decision", REVIEW_DECISIONS), name="review_decision"),
        CheckConstraint(
            "decision <> 'reject' OR (comment IS NOT NULL AND comment <> '')",
            name="review_reject_needs_comment",
        ),
        Index("ix_manual_settlement_review_line", "line_key", "acted_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_key: Mapped[str] = mapped_column(String(512), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[str] = mapped_column(String(8), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    line_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SettlementMonthClose(_ManualAudit, _Timestamps, Base):
    """结账 / 反结账. store_scope is a store id or 'ALL'."""

    __tablename__ = "manual_settlement_month_close"
    __table_args__ = (
        UniqueConstraint("store_scope", "bill_month", name="uq_manual_settlement_month_close"),
        CheckConstraint(_first_of_month("bill_month"), name="month_close_first_day"),
        CheckConstraint(_in("status", MONTH_CLOSE_STATUSES), name="month_close_status"),
        CheckConstraint(
            "status <> 'reopened' OR (reopen_reason IS NOT NULL AND reopen_reason <> '')",
            name="month_close_reopen_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    frozen_calc_version: Mapped[int | None] = mapped_column(Integer)
    snapshot_totals: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


# --------------------------------------------------------------------------- CFG


class NetProfitAllocationConfig(_Timestamps, Base):
    """纯利设置 by effective month. Excluded owners are data (no names in code)."""

    __tablename__ = "cfg_net_profit_allocation"
    __table_args__ = (
        UniqueConstraint("effective_month", name="uq_cfg_net_profit_allocation_month"),
        CheckConstraint(_first_of_month("effective_month"), name="net_profit_cfg_first_day"),
        CheckConstraint("fixed_cny >= 0", name="net_profit_cfg_fixed_nonneg"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    fixed_cny: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("15000"), server_default=text("15000"), nullable=False
    )
    excluded_owner_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


SETTLEMENT_PROFIT_TABLES: tuple[str, ...] = (
    "ods_lingxing_mp_profit_order_lines",
    "ods_walmart_wfs_fee_detail_lines",
    "ods_walmart_storage_fee_lines",
    "ods_walmart_review_accelerator_snapshots",
    "fact_settlement_order_lines",
    "fact_inventory_movement_lines",
    "fact_settlement_unassigned_amounts",
    "fact_settlement_post_close_diffs",
    "mart_settlement_profit_item_month",
    "mart_settlement_order_review",
    "mart_settlement_reconcile_store_month",
    "mart_inventory_movement_month",
    "manual_settlement_order_adjustments",
    "manual_settlement_review_actions",
    "manual_settlement_month_close",
    "cfg_net_profit_allocation",
)
