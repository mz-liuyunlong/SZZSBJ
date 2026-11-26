from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class WalmartBillSyncFailedStore(BaseModel):
    """最近一次同步里没完成的店：哪个店、哪个窗口、领星到底回了什么。"""

    store_id: str
    store_code: str
    window_start: str | None = None  # yyyy-mm-dd
    window_end: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    provider_code: str | None = None
    provider_message: str | None = None


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
    # 最近一次运行失败时，按店列出没完成的店（成功或还在跑时为空）。
    failed_stores: list[WalmartBillSyncFailedStore] = []


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
    payable_source: str = "lingxing"
    walmart_total_payable: Decimal | None = None
    walmart_diff: Decimal | None = None
    walmart_synced_at: datetime | None = None
    amounts_by_type: dict[str, str]
    status: str
    refreshed_at: datetime


class WalmartReconPayoutSyncData(BaseModel):
    """「拉沃尔玛打款额」按钮：只投递任务，结果体现在期次的 payable_source / walmart_synced_at。"""

    status: str = "queued"


class WalmartBillPeriodListData(BaseModel):
    items: list[WalmartBillPeriodRead]
    # 一次最多返回 limit 行；truncated=true 表示还有更早的期没返回，请缩小日期范围或按店查。
    limit: int = 2000
    truncated: bool = False
