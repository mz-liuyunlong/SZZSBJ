"""WFS 费用明细（Rocky 2026-11-12）：一张表、一列费用类型。

- 来源三种：结算报表（SETTLEMENT，服务费各类 + 退货处理费）、仓储费报表（WFS_STORAGE_FEE）、
  入库运输报告（卖家后台）。配送费不入表。
- 一行 = 报表里一笔费用，按 店铺 + line_key 幂等；无 GTIN 的行分摊到商品时，
  子行 parent_line_id 指向原行，原行保留、attribution 记分摊状态。
- 金额口径：我方视角，正 = Walmart 付我们，负 = 扣费（结算报表 Net Payable 取反）。
- 原文件先存档（raw_walmart_wfs_fee_files），再解析；调整另存一张表，不改原行。
"""

from __future__ import annotations

from datetime import date, datetime
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

FEE_SOURCES = ("settlement", "storage", "inbound")
ATTRIBUTIONS = ("matched", "unmatched", "allocated", "allocated_check", "unallocated", "company")
FILE_STATUSES = ("parsed", "rejected", "empty")
ADJUST_KINDS = ("realloc", "company", "verified")
CHECK_STATUSES = ("ok", "diff", "lx_only", "report_only")


class WalmartWfsFeeFile(Base):
    __tablename__ = "raw_walmart_wfs_fee_files"
    __table_args__ = (
        Index("ix_raw_walmart_wfs_fee_files_store", "store_id", "fee_source", "period_end"),
        Index("ix_raw_walmart_wfs_fee_files_sha", "sha256"),
        CheckConstraint("fee_source IN ('settlement','storage','inbound')", name="fee_source"),
        CheckConstraint("origin IN ('upload','sync','history')", name="origin"),
        CheckConstraint("status IN ('parsed','rejected','empty')", name="status"),
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    fee_source: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    declared_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    sync_run_id: Mapped[UUID | None] = mapped_column()
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartWfsFeeLine(Base):
    __tablename__ = "fact_walmart_wfs_fee_lines"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", "line_key", name="uq_wfs_fee_line"),
        Index(
            "ix_fact_walmart_wfs_fee_lines_period",
            "source_account_ref",
            "store_id",
            "report_key",
            "fee_type",
        ),
        Index("ix_fact_walmart_wfs_fee_lines_item", "store_id", "item_id", "date_charged"),
        Index("ix_fact_walmart_wfs_fee_lines_parent", "parent_line_id"),
        CheckConstraint("fee_source IN ('settlement','storage','inbound')", name="fee_source"),
        CheckConstraint(
            "attribution IN ('matched','unmatched','allocated','allocated_check',"
            "'unallocated','company')",
            name="attribution",
        ),
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    fee_source: Mapped[str] = mapped_column(String(16), nullable=False)
    fee_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    line_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_charged: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    report_key: Mapped[str | None] = mapped_column(String(64))
    report_date: Mapped[date | None] = mapped_column(Date)
    bill_match: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    po_number: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    partner_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    gtin: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    msku: Mapped[str] = mapped_column(Text, nullable=False, default="")
    local_sku: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    original_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_savings: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    attribution: Mapped[str] = mapped_column(String(24), nullable=False)
    allocation_basis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_line_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fact_walmart_wfs_fee_lines.id", ondelete="CASCADE")
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    raw_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_walmart_wfs_fee_files.id"), nullable=False
    )
    last_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_walmart_wfs_fee_files.id"), nullable=False
    )
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartWfsFeeAdjustment(Base):
    __tablename__ = "manual_walmart_wfs_fee_adjustments"
    __table_args__ = (
        Index("ix_manual_walmart_wfs_fee_adjustments_line", "line_id"),
        CheckConstraint("kind IN ('realloc','company','verified')", name="kind"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_id: Mapped[UUID] = mapped_column(
        ForeignKey("fact_walmart_wfs_fee_lines.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartWfsFeeCheck(Base):
    """店铺 × 账单期 × 费用类型：领星账单 vs 本表的金额核对。"""

    __tablename__ = "mart_walmart_wfs_fee_checks"
    __table_args__ = (
        CheckConstraint("status IN ('ok','diff','lx_only','report_only')", name="status"),
    )

    source_account_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    report_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    fee_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_date: Mapped[date | None] = mapped_column(Date)
    lingxing_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    lingxing_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    report_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    verified_reason: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )