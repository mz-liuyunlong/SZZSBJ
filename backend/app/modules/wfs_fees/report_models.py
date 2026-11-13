"""WFS 费用报表同步（PR 2）：报表任务 + 入库货件明细。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
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

REPORT_TYPES = ("SETTLEMENT", "WFS_STORAGE_FEE")
ACTIVE_STATUSES = ("queued", "submitted")
DONE_STATUSES = ("imported", "empty", "failed", "pii_blocked")


class WalmartWfsReportJob(Base):
    """一店 × 一类报表 × 一期：下单 → 等沃尔玛生成 → 下载 → 导入 WFS 费用明细。"""

    __tablename__ = "ops_walmart_wfs_report_jobs"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('SETTLEMENT','WFS_STORAGE_FEE')", name="report_type_whitelist"
        ),
        CheckConstraint("origin IN ('schedule','manual')", name="origin"),
        CheckConstraint(
            "status IN ('queued','submitted','imported','empty','failed','pii_blocked')",
            name="status",
        ),
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        CheckConstraint("period_end >= period_start", name="period_order"),
        Index(
            "uq_ops_walmart_wfs_report_jobs_active",
            "source_account_ref",
            "store_id",
            "report_type",
            "period_start",
            "period_end",
            unique=True,
            postgresql_where=text("status IN ('queued','submitted')"),
        ),
        Index("ix_ops_walmart_wfs_report_jobs_due", "status", "next_action_at"),
        Index("ix_ops_walmart_wfs_report_jobs_store", "store_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    submit_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    polls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 连续几次远端没跑成（连不上 / 执行器没回应 / 令牌被拒）；跑成一次清零，满 48 次失败
    remote_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    file_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    last_run_id: Mapped[UUID | None] = mapped_column()
    next_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartWfsInboundItem(Base):
    """入库货件明细（沃尔玛远程采集的 inbound_shipment_items）：入库运费按实发数量分到商品。"""

    __tablename__ = "fact_walmart_wfs_inbound_items"
    __table_args__ = (
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "shipment_id",
            "gtin",
            "sku",
            name="uq_wfs_inbound_item",
        ),
        Index("ix_fact_walmart_wfs_inbound_items_shipment", "store_id", "shipment_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gtin: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    sku: Mapped[str] = mapped_column(Text, nullable=False, default="")
    item_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    received_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source_run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
