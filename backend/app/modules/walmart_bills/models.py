"""沃尔玛账单（领星 statement/list）：明细表 + 按「店铺 × 每期」汇总表。

回款对账、现金利润、结算利润三个板块共用这一层，只由同步任务写入。
- 原始响应先进系统共用的原始层（ods_api_raw_blobs / ods_api_raw_request_refs）。
- 明细表一行 = 领星一条账单明细（按领星行 id 去重）；收货地址字段不落业务层。
- 汇总表一行 = 一个店铺的一期账单（reportKey），一期 = 一次打款。
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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WalmartBillLine(Base):
    """领星沃尔玛账单明细。missing_since 不为空 = 最近一次重拉同一时间段时领星不再返回这一行。

    行身份 line_key = 组合键（领星行号、账单、交易、订单行、金额类型、描述、金额、交易时间）
    + 同组合键出现序号的摘要；领星事后改了金额，表现为旧行 missing、新行插入。
    """

    __tablename__ = "ods_lingxing_walmart_bill_lines"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "line_key",
            name="uq_ods_lingxing_walmart_bill_lines_line",
        ),
        Index("ix_walmart_bill_lines_store_lx_line", "store_id", "lx_line_id"),
        Index("ix_walmart_bill_lines_store_posted", "store_id", "posted_date"),
        Index("ix_walmart_bill_lines_store_report", "store_id", "report_key"),
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        CheckConstraint("delete_flag IN (0, 1)", name="delete_flag"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    line_key: Mapped[str] = mapped_column(String(64), nullable=False)
    lx_line_id: Mapped[str] = mapped_column(String(32), nullable=False)
    report_key: Mapped[str] = mapped_column(String(64), nullable=False)
    report_id: Mapped[str | None] = mapped_column(String(32))
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start_date: Mapped[date | None] = mapped_column(Date)
    period_end_date: Mapped[date | None] = mapped_column(Date)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    posted_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_key: Mapped[str | None] = mapped_column(String(128))
    transaction_type: Mapped[str | None] = mapped_column(String(128))
    transaction_description: Mapped[str | None] = mapped_column(Text)
    transaction_reason_description: Mapped[str | None] = mapped_column(Text)
    amount_type: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    total_payable: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ship_qty: Mapped[int | None] = mapped_column(Integer)
    customer_order_no: Mapped[str | None] = mapped_column(String(64))
    customer_order_line_no: Mapped[str | None] = mapped_column(String(32))
    purchase_order_no: Mapped[str | None] = mapped_column(String(64))
    purchase_order_line_no: Mapped[str | None] = mapped_column(String(32))
    partner_item_id: Mapped[str | None] = mapped_column(String(64))
    partner_gtin: Mapped[str | None] = mapped_column(String(32))
    fulfillment_type: Mapped[str | None] = mapped_column(String(64))
    unique_no: Mapped[str | None] = mapped_column(String(64))
    delete_flag: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # 其余字段（佣金、商品名、类目等）原样留存给结算利润用；收货城市 / 州 / 邮编不进这里。
    extra_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL")
    )
    first_seen_run_id: Mapped[UUID | None] = mapped_column()
    last_seen_run_id: Mapped[UUID | None] = mapped_column()
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WalmartBillPeriod(Base):
    """按「店铺 × 一期账单」汇总。应付金额 = 账单总额（领星有给时），否则 = 有效明细合计。"""

    __tablename__ = "mart_walmart_bill_periods"
    __table_args__ = (
        Index("ix_walmart_bill_periods_report_date", "report_date"),
        CheckConstraint("status IN ('normal', 'not_payable', 'voided')", name="status"),
    )

    source_account_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    report_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    store_name: Mapped[str | None] = mapped_column(String(255))
    report_id: Mapped[str | None] = mapped_column(String(32))
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start_date: Mapped[date | None] = mapped_column(Date)
    period_end_date: Mapped[date | None] = mapped_column(Date)
    first_posted_date: Mapped[date | None] = mapped_column(Date)
    last_posted_date: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str | None] = mapped_column(String(8))
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_sum: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_payable: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    payable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amounts_by_type: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_run_id: Mapped[UUID | None] = mapped_column()
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
