"""Gate 3 tables for the PMC purchase board: DWD ×3, DWS ×3, manual ×1, rule ×1.

Layering (docs/data-sources/database-layering-standard.md, PRP §6, rules v4 §7):

* ``dwd_purchase_*`` — one row per *current* document version, derived from the ODS
  tables by ``dwd_builder`` (newest ``update_time`` wins). No provider JSON here; the
  raw record stays in ODS and is reachable through ``source_ods_id`` / ``source_run_id``.
* ``dws_purchase_*`` — what the board reads. Rebuilt by the DWS refresh (delete+insert
  per account, ``calc_version`` + ``source_lineage_json`` like the DATA-PAGES marts).
  The frontend reads only these three tables.
* ``manual_purchase_cycle_override`` — human corrections to the SKU purchase cycle
  (exclude / restore / arrival_date / baseline). Append-only: a correction is undone by
  a newer record, never by deleting history (docs/MANUAL_OVERRIDE_BOUNDARY_RULES.md).
  There is deliberately **no** ItemID override table (Owner decision 2026-09-21, #144).
* ``rule_purchase_thresholds`` — versioned rule parameters; the defaults of
  ``calculations.PurchaseThresholds`` are its first version.

Time columns are Beijing calendar dates (rules §3.2); ids stay strings; money is
``Numeric(18, 4)`` with a sibling currency code.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base

PROVIDER_ID = String(64)
MONEY = Numeric(18, 4)
RATIO = Numeric(18, 6)
ITEM_ID = String(32)

ITEM_ID_SOURCES = (
    "'from_system_plan', 'from_plan_remark', 'from_packing_slip', "
    "'pending_packing_slip', 'unresolved'"
)
STAGE_CODES = "'S1', 'S2', 'S3', 'S4', 'S9', 'S0', 'UNKNOWN'"
CYCLE_SOURCES = "'samples', 'baseline_mix', 'lingxing_default', 'no_baseline'"
PENDING_TYPES = "'itemid_pending', 'wfs_not_ready', 'overdue'"
OVERRIDE_KINDS = "'exclude', 'restore', 'arrival_date', 'baseline'"


def utc_now() -> datetime:
    return datetime.now(UTC)


# --- shared column groups ---------------------------------------------------------------


class DwdSourceMixin:
    """Where the current version of a DWD row came from (lineage without JSON)."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    @declared_attr
    @classmethod
    def source_run_id(cls) -> Mapped[UUID]:
        return mapped_column(
            ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
        )

    # ODS row the current version was taken from (no FK: the ODS table differs per DWD table).
    source_ods_id: Mapped[UUID] = mapped_column(nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_update_time: Mapped[str | None] = mapped_column(String(32))
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class DwsCalcMixin:
    """Refresh provenance shared by the three DWS tables (DATA-PAGES mart convention)."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    calc_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_lineage_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


# --- DWD ------------------------------------------------------------------------------------


class DwdPurchasePlan(DwdSourceMixin, Base):
    """Current version of a purchase plan (rules §1, §5.1; aux/combo plans excluded)."""

    __tablename__ = "dwd_purchase_plan"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "plan_sn", name="uq_dwd_purchase_plan_sn"),
        CheckConstraint("char_length(trim(plan_sn)) > 0", name="nonblank_plan_sn"),
        Index("ix_dwd_purchase_plan_sku", "sku"),
        Index("ix_dwd_purchase_plan_status", "status"),
    )

    plan_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    create_date: Mapped[date | None] = mapped_column(Date)
    expect_arrive_date: Mapped[date | None] = mapped_column(Date)
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_attributed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # ``store_id`` found in dim_lingxing_stores (rules §1.1: unresolved ids keep their value).
    store_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(Text)
    quantity_plan: Mapped[int | None] = mapped_column(Integer)
    remark: Mapped[str | None] = mapped_column(Text)
    remark_item_id: Mapped[str | None] = mapped_column(ITEM_ID)
    # §2 S2 start: first date the system observed status=2; NULL until seen incrementally.
    first_seen_pending_date: Mapped[date | None] = mapped_column(Date)


class DwdPurchaseOrder(DwdSourceMixin, Base):
    """Current version of a purchase order header (rules §1, §6)."""

    __tablename__ = "dwd_purchase_order"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "order_sn", name="uq_dwd_purchase_order_sn"),
        CheckConstraint("char_length(trim(order_sn)) > 0", name="nonblank_order_sn"),
        Index("ix_dwd_purchase_order_status", "status"),
        Index("ix_dwd_purchase_order_order_date", "order_date"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    order_date: Mapped[date | None] = mapped_column(Date)
    create_date: Mapped[date | None] = mapped_column(Date)
    quantity_total: Mapped[int | None] = mapped_column(Integer)
    quantity_receive: Mapped[int | None] = mapped_column(Integer)
    quantity_real: Mapped[int | None] = mapped_column(Integer)
    amount_total: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str | None] = mapped_column(String(16))
    purchase_rate: Mapped[Decimal | None] = mapped_column(RATIO)
    shipping_price: Mapped[Decimal | None] = mapped_column(MONEY)
    other_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)


class DwdPurchaseOrderLineItem(DwdSourceMixin, Base):
    """Purchase-order line × plan (merged lines split by plan quantity, rules §5.2)."""

    __tablename__ = "dwd_purchase_order_line_item"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dwd_purchase_order_line_item_key",
        ),
        CheckConstraint("char_length(trim(order_sn)) > 0", name="nonblank_order_sn"),
        CheckConstraint("char_length(trim(order_item_id)) > 0", name="nonblank_order_item_id"),
        CheckConstraint("line_ordinal >= 0", name="line_ordinal"),
        CheckConstraint("plan_count >= 0", name="plan_count"),
        CheckConstraint("quantity_allocated >= 0", name="quantity_allocated"),
        CheckConstraint("allocation_ratio >= 0 AND allocation_ratio <= 1", name="allocation_ratio"),
        Index("ix_dwd_purchase_order_line_item_order_sn", "order_sn"),
        Index("ix_dwd_purchase_order_line_item_plan_sn", "plan_sn"),
        Index("ix_dwd_purchase_order_line_item_sku", "sku"),
        Index("ix_dwd_purchase_order_line_item_store_id", "store_id"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    # Lingxing ``item_list.id``; receipt lines reference it as ``order_item_id``.
    order_item_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    # ``plan_sn`` or ``''`` so the unique key works for lines without a plan.
    plan_key: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False, server_default=text("''"))
    plan_count: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_ratio: Mapped[Decimal] = mapped_column(RATIO, nullable=False)
    is_merged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    plan_found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_attributed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    store_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(Text)
    quantity_plan: Mapped[int | None] = mapped_column(Integer)
    quantity_real: Mapped[int | None] = mapped_column(Integer)
    quantity_allocated: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_allocated: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    expect_arrive_date: Mapped[date | None] = mapped_column(Date)
    remark_item_id: Mapped[str | None] = mapped_column(ITEM_ID)


# --- DWS ------------------------------------------------------------------------------------


class DwsPurchaseBoard(DwsCalcMixin, Base):
    """Board row = one DWD line (order × line × plan) with every derived metric (PRP §7.1)."""

    __tablename__ = "dws_purchase_board"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dws_purchase_board_key",
        ),
        CheckConstraint(f"stage_code IN ({STAGE_CODES})", name="stage_code"),
        CheckConstraint(f"item_id_source IN ({ITEM_ID_SOURCES})", name="item_id_source"),
        CheckConstraint("overdue_days >= 0", name="overdue_days"),
        Index("ix_dws_purchase_board_stage_code", "stage_code"),
        Index("ix_dws_purchase_board_store_id", "store_id"),
        Index("ix_dws_purchase_board_sku", "sku"),
        Index("ix_dws_purchase_board_item_id", "item_id"),
        Index("ix_dws_purchase_board_owner_uid", "owner_uid"),
        Index("ix_dws_purchase_board_order_date", "order_date"),
    )

    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    order_item_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    plan_key: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False, server_default=text("''"))
    plan_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    plan_sns_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    order_status: Mapped[int | None] = mapped_column(Integer)
    plan_status: Mapped[int | None] = mapped_column(Integer)
    # §2 stage / overdue
    stage_code: Mapped[str] = mapped_column(String(8), nullable=False)
    stage_start: Mapped[date | None] = mapped_column(Date)
    threshold_days: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    overdue_days: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_due_since: Mapped[date | None] = mapped_column(Date)
    stage_start_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # identity / attribution
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    store_name: Mapped[str | None] = mapped_column(String(255))
    store_attributed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(Text)
    msku: Mapped[str | None] = mapped_column(String(255))
    gtin: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(ITEM_ID)
    item_id_source: Mapped[str] = mapped_column(String(32), nullable=False)
    # #144 condition 7: source document (plan sn / packing slip no), match time and status.
    item_id_source_ref: Mapped[str | None] = mapped_column(PROVIDER_ID)
    item_id_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_id_match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_uid: Mapped[str | None] = mapped_column(String(255))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    fulfillment_type: Mapped[str | None] = mapped_column(String(64))
    wfs_not_ready: Mapped[bool | None] = mapped_column(Boolean)
    # §3 quantities / arrival
    quantity_total: Mapped[int | None] = mapped_column(Integer)
    quantity_allocated: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_ratio: Mapped[Decimal | None] = mapped_column(RATIO)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_date: Mapped[date | None] = mapped_column(Date)
    order_create_date: Mapped[date | None] = mapped_column(Date)
    plan_create_date: Mapped[date | None] = mapped_column(Date)
    arrival_date: Mapped[date | None] = mapped_column(Date)
    arrival_receipt_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    # §4 cycles
    purchase_cycle_days: Mapped[int | None] = mapped_column(Integer)
    approval_cycle_days: Mapped[int | None] = mapped_column(Integer)
    sku_cycle_days: Mapped[Decimal | None] = mapped_column(MONEY)
    sku_cycle_source: Mapped[str | None] = mapped_column(String(32))
    sku_cycle_sample_count: Mapped[int | None] = mapped_column(Integer)
    sku_cycle_unstable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # §6 money (as delivered, no FX)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    amount_allocated: Mapped[Decimal | None] = mapped_column(MONEY)
    amount_total: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str | None] = mapped_column(String(16))


class DwsPurchaseSkuCycle(DwsCalcMixin, Base):
    """SKU actual purchase cycle (rules §4.2 / §4.4; PRP §7.4)."""

    __tablename__ = "dws_purchase_sku_cycle"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "sku", name="uq_dws_purchase_sku_cycle_sku"),
        CheckConstraint(f"source IN ({CYCLE_SOURCES})", name="source"),
        CheckConstraint("sample_count >= 0", name="sample_count"),
        Index("ix_dws_purchase_sku_cycle_unstable", "unstable"),
    )

    sku: Mapped[str] = mapped_column(String(255), nullable=False)
    value_days: Mapped[Decimal | None] = mapped_column(MONEY)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_days: Mapped[int | None] = mapped_column(Integer)
    baseline_set_on: Mapped[date | None] = mapped_column(Date)
    lingxing_default_days: Mapped[int | None] = mapped_column(Integer)
    unstable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    range_days: Mapped[int | None] = mapped_column(Integer)
    # Newest 5 considered orders incl. excluded ones (order_sn, dates, days, used, exclusion).
    samples_json: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)


class DwsPurchasePending(DwsCalcMixin, Base):
    """Pending lists (PRP §7.2 cards / §8 filters): ItemID pending, WFS not ready, overdue."""

    __tablename__ = "dws_purchase_pending"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "pending_type",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dws_purchase_pending_key",
        ),
        CheckConstraint(f"pending_type IN ({PENDING_TYPES})", name="pending_type"),
        Index("ix_dws_purchase_pending_type", "pending_type"),
        Index("ix_dws_purchase_pending_owner_uid", "owner_uid"),
    )

    pending_type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_sn: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    order_item_id: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False)
    plan_key: Mapped[str] = mapped_column(PROVIDER_ID, nullable=False, server_default=text("''"))
    plan_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    sku: Mapped[str | None] = mapped_column(String(255))
    store_id: Mapped[str | None] = mapped_column(PROVIDER_ID)
    item_id: Mapped[str | None] = mapped_column(ITEM_ID)
    item_id_source: Mapped[str | None] = mapped_column(String(32))
    stage_code: Mapped[str | None] = mapped_column(String(8))
    overdue_days: Mapped[int | None] = mapped_column(Integer)
    owner_uid: Mapped[str | None] = mapped_column(String(255))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    detail_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


# --- manual / rule ---------------------------------------------------------------------------


class ManualPurchaseCycleOverride(Base):
    """Human correction to a SKU purchase cycle (rules §4.2; PRP §7.5).

    Append-only. ``kind``: exclude / restore one order from the samples, arrival_date
    (override one order's arrival date), baseline (set the whole-SKU baseline). Undo =
    a newer record (``restore`` or a new baseline); ``effective_to`` closes a record.
    """

    __tablename__ = "manual_purchase_cycle_override"
    __table_args__ = (
        CheckConstraint(f"kind IN ({OVERRIDE_KINDS})", name="kind"),
        CheckConstraint("char_length(trim(reason)) > 0", name="nonblank_reason"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_period"
        ),
        Index("ix_manual_purchase_cycle_override_sku_active", "sku", "is_active"),
        Index("ix_manual_purchase_cycle_override_order_sn", "purchase_order_sn"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    purchase_order_sn: Mapped[str | None] = mapped_column(PROVIDER_ID)
    value_days: Mapped[int | None] = mapped_column(Integer)
    value_date: Mapped[date | None] = mapped_column(Date)
    before_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    after_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RulePurchaseThresholds(Base):
    """Versioned rule parameters (rules §2, §3.2, §4.2, §4.4; AGENTS.md §8).

    One row per version; the active version is the one with ``is_active`` and the
    latest ``effective_from`` ≤ today. Changes go through a PR/SQL with
    ``approved_by`` / ``change_reason`` (no API in Gate 3, Rocky 2026-09-21).
    """

    __tablename__ = "rule_purchase_thresholds"
    __table_args__ = (
        UniqueConstraint("rule_key", "version", name="uq_rule_purchase_thresholds_version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("arrival_ratio > 0 AND arrival_ratio <= 1", name="arrival_ratio"),
        CheckConstraint("sample_window >= 1", name="sample_window"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_period"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'pmc_purchase_thresholds'")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    s1_approval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    s2_pending_days: Mapped[int] = mapped_column(Integer, nullable=False)
    default_cycle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    auto_exclude_below_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_window: Mapped[int] = mapped_column(Integer, nullable=False)
    min_samples_for_average: Mapped[int] = mapped_column(Integer, nullable=False)
    unstable_min_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    unstable_range_days: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_evict_at_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


PMC_PURCHASE_GATE3_TABLES: tuple[str, ...] = (
    DwdPurchasePlan.__tablename__,
    DwdPurchaseOrder.__tablename__,
    DwdPurchaseOrderLineItem.__tablename__,
    DwsPurchaseBoard.__tablename__,
    DwsPurchaseSkuCycle.__tablename__,
    DwsPurchasePending.__tablename__,
    ManualPurchaseCycleOverride.__tablename__,
    RulePurchaseThresholds.__tablename__,
)
