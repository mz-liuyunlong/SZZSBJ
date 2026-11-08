from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class WalmartBillSyncData(BaseModel):
    """「手动同步」按钮和页面顶部的同步状态。"""

    run_id: UUID | None = None
    status: str = "never"  # never / queued / running / succeeded / failed
    trigger_type: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    records_seen: int = 0
    records_written: int = 0
    last_success_at: datetime | None = None


class WalmartBillPeriodRead(BaseModel):
    """一个店铺的一期沃尔玛账单（一期 = 一次打款）。不含订单号、买家信息。"""

    store_id: str
    store_name: str | None
    report_key: str
    report_date: date
    period_start_date: date | None
    period_end_date: date | None
    currency_code: str | None
    line_count: int
    excluded_line_count: int
    amount_sum: Decimal
    total_payable: Decimal | None
    payable_amount: Decimal
    amounts_by_type: dict[str, str]
    status: str
    refreshed_at: datetime


class WalmartBillPeriodListData(BaseModel):
    items: list[WalmartBillPeriodRead]
