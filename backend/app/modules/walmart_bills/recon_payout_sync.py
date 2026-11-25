"""把沃尔玛对账报表的每期打款额写到 mart_walmart_bill_periods（0097）。

一次同步：每家店 1 次「可用日期」+ 每个缺的日期 1 次「第一页」（100 行），只读 GET，走 V4
通用通道（call_walmart）。只允许 recon_payout.ALLOWED_PATHS 这两个路径，别的路径一律不调。
领星比沃尔玛晚 1~3 天出账单：沃尔玛有、领星还没有这期的先跳过，下次再补。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.walmart_bills.models import WalmartBillPeriod
from app.modules.walmart_bills.periods import period_status
from app.modules.walmart_bills.recon_payout import (
    ALLOWED_PATHS,
    RECON_DATES_PATH,
    RECON_FILE_PATH,
    RECON_PAGE_SIZE,
    PaymentSummary,
    ReconPayoutError,
    extract_payment_summary,
    lingxing_payable,
    parse_available_dates,
    report_date_param,
    utc_now,
)

ENABLED_ENV: Final = "SZZSBJ_WALMART_RECON_PAYOUT_ENABLED"
# 领星账单从 2026-03 起（walmart_bill_catalog.WALMART_BILL_EARLIEST_DATE），
# 沃尔玛可用日期也只到半年左右；
# 往期一次补齐（Rocky 2026-11-26），每店最多这么多期、每期只拉第一页
LOOKBACK_DAYS: Final = 400
MAX_DATES_PER_STORE: Final = 40
SOURCE_REF: Final = "primary"

# 和 call_walmart 同形：store_code, method, path, query=, response_kind=
# → 带 status_code / data 的结果
WalmartCall = Callable[..., Any]


@dataclass(slots=True)
class StoreOutcome:
    store_code: str
    fetched: int = 0
    written: int = 0
    skipped_no_period: int = 0
    error: str | None = None


@dataclass(slots=True)
class ReconPayoutSyncResult:
    started_at: datetime
    finished_at: datetime | None = None
    stores: list[StoreOutcome] = field(default_factory=list)

    @property
    def written(self) -> int:
        return sum(s.written for s in self.stores)

    @property
    def failed(self) -> list[str]:
        return [s.store_code for s in self.stores if s.error]


def _get(call: WalmartCall, store_code: str, path: str, query: Mapping[str, Any]) -> Any:
    if path not in ALLOWED_PATHS:
        raise ReconPayoutError("WALMART_RECON_PATH_NOT_ALLOWED")
    result = call(store_code, "GET", path, query=dict(query), response_kind="json")
    code = getattr(result, "status_code", None)
    if code != 200:
        raise ReconPayoutError(f"WALMART_RECON_HTTP_{code}")
    return getattr(result, "data", None)


def fetch_store_summaries(
    call: WalmartCall,
    *,
    store_code: str,
    wanted: Callable[[date], bool],
    today: date,
) -> list[PaymentSummary]:
    """可用日期里最近 LOOKBACK_DAYS 内、wanted() 为真的日期，各取第一页的 PaymentSummary。"""
    dates = parse_available_dates(_get(call, store_code, RECON_DATES_PATH, {"reportVersion": "v1"}))
    floor = today - timedelta(days=LOOKBACK_DAYS)
    picked = [d for d in dates if d >= floor and wanted(d)][-MAX_DATES_PER_STORE:]
    out: list[PaymentSummary] = []
    for report_date in picked:
        payload = _get(
            call,
            store_code,
            RECON_FILE_PATH,
            {
                "reportDate": report_date_param(report_date),
                "offset": 0,
                "noOfRecords": RECON_PAGE_SIZE,
            },
        )
        out.append(extract_payment_summary(report_date, payload))
    return out


def apply_summary(
    session: Session, row: WalmartBillPeriod, summary: PaymentSummary, *, now: datetime
) -> None:
    """写到这一期：应付 = 沃尔玛打款额，差额 = 沃尔玛 − 领星，状态按沃尔玛金额重算。"""
    lingxing = lingxing_payable(row)
    row.walmart_total_payable = summary.total_payable
    row.walmart_diff = summary.total_payable - lingxing
    row.payable_source = "walmart"
    row.payable_amount = summary.total_payable
    row.walmart_period_start_date = summary.period_start_date
    row.walmart_period_end_date = summary.period_end_date
    row.walmart_posted_date = summary.posted_date
    row.walmart_account_rows = list(summary.account_rows)
    row.walmart_synced_at = now
    row.status = period_status(valid_lines=row.line_count, payable=summary.total_payable)
    session.add(row)


def sync_recon_payouts(
    session: Session,
    *,
    call: WalmartCall,
    store_codes: Mapping[str, str],
    source_account_ref: str = SOURCE_REF,
    today: date | None = None,
    now: datetime | None = None,
    refresh_existing: bool = False,
) -> ReconPayoutSyncResult:
    """store_codes: 领星 store_id → 沃尔玛店铺编码（reviewed_store_id_map）。

    一店一个保存点，失败整店回滚。
    """
    now = now or utc_now()
    today = today or now.date()
    result = ReconPayoutSyncResult(started_at=now)
    for store_id, store_code in sorted(store_codes.items(), key=lambda item: item[1]):
        outcome = StoreOutcome(store_code=store_code)
        result.stores.append(outcome)
        periods = {
            row.report_date: row
            for row in session.scalars(
                select(WalmartBillPeriod).where(
                    WalmartBillPeriod.source_account_ref == source_account_ref,
                    WalmartBillPeriod.store_id == store_id,
                    WalmartBillPeriod.report_date >= today - timedelta(days=LOOKBACK_DAYS),
                )
            )
        }

        def wanted(report_date: date, periods: dict[date, WalmartBillPeriod] = periods) -> bool:
            row = periods.get(report_date)
            return row is not None and (refresh_existing or row.walmart_total_payable is None)

        savepoint = session.begin_nested()
        try:
            summaries = fetch_store_summaries(
                call, store_code=store_code, wanted=wanted, today=today
            )
            outcome.fetched = len(summaries)
            for summary in summaries:
                row = periods.get(summary.report_date)
                if row is None:
                    outcome.skipped_no_period += 1
                    continue
                apply_summary(session, row, summary, now=now)
                outcome.written += 1
            session.flush()
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            outcome.error = exc.args[0] if isinstance(exc, ReconPayoutError) else type(exc).__name__
    result.finished_at = utc_now()
    return result


def enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(ENABLED_ENV, "").strip() == "1"


def production_call() -> WalmartCall:
    from app.integrations.walmart.generic_client import call_walmart

    return call_walmart


def production_store_codes(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    from app.integrations.walmart.gateway import reviewed_store_id_map

    return reviewed_store_id_map(environ)


ZERO: Final = Decimal("0")
