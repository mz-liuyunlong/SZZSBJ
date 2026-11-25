"""把沃尔玛对账报表的每期打款额写到 mart_walmart_bill_periods（0097）。

一次同步：每家店 1 次「可用日期」+ 每个缺的期 1 次「第一页」（100 行），只读 GET，走 V4
通用通道（call_walmart）。只允许 recon_payout.ALLOWED_PATHS 这两个路径，别的路径一律不调。
- 只拉账单日 ≥ RECON_PAYOUT_START（2026-11-01）的期：10 月及以前已人工对完，不碰
  （Rocky 2026-11-26）。
- 每页先原样落 raw_walmart_recon_report_pages（RAW），再解析写期表。
- 每期先把原始页单独落 RAW（独立保存点，拉到就留下），再开第二个保存点解析写期表：解析失败只回滚
  期表改动，RAW 保留；每店结束后单独提交（限流时这家店已拉到的 RAW 和已写的期也保留）。
- 领星比沃尔玛晚 1~3 天出账单：沃尔玛有、领星还没有这期的先跳过，下次再补。
- 这期已配对或审核过、应付变化 > 0.01：照改应付，追加一条 reset 审核事件退回待初审，任务结果列出。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.walmart_bills import payout_match as rules
from app.modules.walmart_bills.models import WalmartBillPeriod, WalmartReconReportPage
from app.modules.walmart_bills.payout_models import WalmartPayoutMatch, WalmartPayoutReviewEvent
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
# 只拉这一天起的账单日（Rocky 2026-11-26：10 月已人工对完，不拉、不改）
RECON_PAYOUT_START: Final = date(2026, 11, 1)
MAX_DATES_PER_STORE: Final = 40
SOURCE_REF: Final = "primary"
TOLERANCE: Final = Decimal("0.01")
SYNC_ACTOR: Final = "walmart-recon-payout-sync"

# 和 call_walmart 同形：store_code, method, path, query=, response_kind=
# → 带 status_code / data / request_id 的结果
WalmartCall = Callable[..., Any]


@dataclass(slots=True)
class PeriodOutcome:
    report_date: date
    status: str  # written / skipped_no_period / reset / error
    error: str | None = None


@dataclass(slots=True)
class StoreOutcome:
    store_code: str
    periods: list[PeriodOutcome] = field(default_factory=list)
    error: str | None = None

    @property
    def written(self) -> int:
        return sum(1 for p in self.periods if p.status in ("written", "reset"))

    @property
    def reset(self) -> list[date]:
        return [p.report_date for p in self.periods if p.status == "reset"]

    @property
    def failed_periods(self) -> list[tuple[date, str]]:
        return [(p.report_date, p.error or "") for p in self.periods if p.status == "error"]


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

    @property
    def reset(self) -> list[tuple[str, date]]:
        return [(s.store_code, d) for s in self.stores for d in s.reset]


def _error_code(exc: BaseException) -> str:
    """ReconPayoutError / GatewayRejected 的 args[0] 都是过滤过的稳定码；别的只记类名。"""
    text = str(exc.args[0]) if exc.args else ""
    if type(exc).__name__ in ("ReconPayoutError", "GatewayRejected") and text:
        return text[:128]
    return type(exc).__name__


def _get(call: WalmartCall, store_code: str, path: str, query: Mapping[str, Any]) -> Any:
    if path not in ALLOWED_PATHS:
        raise ReconPayoutError("WALMART_RECON_PATH_NOT_ALLOWED")
    result = call(store_code, "GET", path, query=dict(query), response_kind="json")
    code = getattr(result, "status_code", None)
    if code == 429:
        raise ReconPayoutError("WALMART_RECON_RATE_LIMITED")
    if code != 200:
        raise ReconPayoutError(f"WALMART_RECON_HTTP_{code}")
    return result


def _store_raw_page(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str,
    store_code: str,
    report_date: date,
    payload: Any,
    request_id: str | None,
    now: datetime,
) -> WalmartReconReportPage:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    existing = session.get(WalmartReconReportPage, (source_account_ref, store_id, report_date, 0))
    page = WalmartReconReportPage(
        source_account_ref=source_account_ref,
        store_id=store_id,
        store_code=store_code,
        report_date=report_date,
        page_offset=0,
        payload=payload,
        payload_bytes=len(body.encode("utf-8")),
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        request_id=request_id,
        received_at=now,
        previous_sha256=existing.sha256 if existing and existing.sha256 else None,
    )
    session.merge(page)
    return page


def _period_is_in_review(session: Session, row: WalmartBillPeriod) -> bool:
    """有生效配对，或审核阶段不是待初审。"""
    matched = session.scalar(
        select(WalmartPayoutMatch.id)
        .where(
            WalmartPayoutMatch.source_account_ref == row.source_account_ref,
            WalmartPayoutMatch.store_id == row.store_id,
            WalmartPayoutMatch.report_key == row.report_key,
            WalmartPayoutMatch.undone_at.is_(None),
        )
        .limit(1)
    )
    if matched is not None:
        return True
    kinds = session.scalars(
        select(WalmartPayoutReviewEvent.kind)
        .where(
            WalmartPayoutReviewEvent.source_account_ref == row.source_account_ref,
            WalmartPayoutReviewEvent.store_id == row.store_id,
            WalmartPayoutReviewEvent.report_key == row.report_key,
        )
        .order_by(WalmartPayoutReviewEvent.seq_no)
    ).all()
    return rules.stage_of(kinds) != rules.STAGE_TODO


def apply_summary(
    session: Session, row: WalmartBillPeriod, summary: PaymentSummary, *, now: datetime
) -> bool:
    """写到这一期：应付 = 沃尔玛打款额，差额 = 沃尔玛 − 领星，状态按沃尔玛金额重算。

    账期起止、币种和领星对不上就拒绝（ReconPayoutError）。返回是否追加了 reset 事件。
    """
    if row.currency_code and summary.currency_code and row.currency_code != summary.currency_code:
        raise ReconPayoutError("WALMART_RECON_CURRENCY_MISMATCH")
    if (
        row.period_start_date
        and summary.period_start_date
        and abs((row.period_start_date - summary.period_start_date).days) > 3
    ) or (
        row.period_end_date
        and summary.period_end_date
        and abs((row.period_end_date - summary.period_end_date).days) > 3
    ):
        raise ReconPayoutError("WALMART_RECON_PERIOD_MISMATCH")
    before = row.payable_amount
    lingxing = lingxing_payable(row)
    row.walmart_total_payable = summary.total_payable
    row.walmart_diff = summary.total_payable - lingxing
    row.payable_source = "walmart"
    row.payable_amount = summary.total_payable
    row.walmart_period_start_date = summary.period_start_date
    row.walmart_period_end_date = summary.period_end_date
    row.walmart_posted_date = summary.posted_date
    row.walmart_account_rows = list(summary.account_rows)
    row.walmart_account_rows_complete = not summary.has_more
    row.walmart_synced_at = now
    row.status = period_status(valid_lines=row.line_count, payable=summary.total_payable)
    session.add(row)
    changed = abs(before - summary.total_payable) > TOLERANCE
    if changed and _period_is_in_review(session, row):
        session.add(
            WalmartPayoutReviewEvent(
                source_account_ref=row.source_account_ref,
                store_id=row.store_id,
                report_key=row.report_key,
                kind=rules.KIND_RESET,
                reason="沃尔玛对账报表打款额与原应付不一致，退回待初审",
                payload={
                    "payable_before": str(before),
                    "payable_after": str(summary.total_payable),
                },
                actor=SYNC_ACTOR,
            )
        )
        return True
    return False


def _sync_store(
    session: Session,
    *,
    call: WalmartCall,
    store_id: str,
    store_code: str,
    source_account_ref: str,
    now: datetime,
    refresh_existing: bool,
    outcome: StoreOutcome,
) -> None:
    rows = session.scalars(
        select(WalmartBillPeriod)
        .where(
            WalmartBillPeriod.source_account_ref == source_account_ref,
            WalmartBillPeriod.store_id == store_id,
            WalmartBillPeriod.report_date >= RECON_PAYOUT_START,
        )
        .with_for_update()
    ).all()
    periods: dict[date, WalmartBillPeriod] = {}
    duplicated: set[date] = set()
    for row in rows:
        if row.report_date in periods:
            duplicated.add(row.report_date)
        periods[row.report_date] = row
    dates = parse_available_dates(
        _get(call, store_code, RECON_DATES_PATH, {"reportVersion": "v1"}).data
    )
    picked = [
        d
        for d in dates
        if d >= RECON_PAYOUT_START
        and d in periods
        and (refresh_existing or periods[d].walmart_total_payable is None)
    ][-MAX_DATES_PER_STORE:]
    for report_date in picked:
        if report_date in duplicated:
            outcome.periods.append(
                PeriodOutcome(report_date, "error", "WALMART_RECON_DUPLICATE_PERIOD")
            )
            continue
        # 第一步：拉第一页并原样落 RAW（拉到就留下，后面解析失败也不回滚）
        try:
            result = _get(
                call,
                store_code,
                RECON_FILE_PATH,
                {
                    "reportDate": report_date_param(report_date),
                    "offset": 0,
                    "noOfRecords": RECON_PAGE_SIZE,
                },
            )
        except Exception as exc:
            code = _error_code(exc)
            outcome.periods.append(PeriodOutcome(report_date, "error", code))
            if code == "WALMART_RECON_RATE_LIMITED":
                raise
            continue
        raw_point = session.begin_nested()
        try:
            _store_raw_page(
                session,
                source_account_ref=source_account_ref,
                store_id=store_id,
                store_code=store_code,
                report_date=report_date,
                payload=result.data,
                request_id=getattr(result, "request_id", None),
                now=now,
            )
            session.flush()
            raw_point.commit()
        except Exception as exc:
            raw_point.rollback()
            outcome.periods.append(PeriodOutcome(report_date, "error", _error_code(exc)))
            continue
        # 第二步：解析写期表；失败只回滚这一步
        savepoint = session.begin_nested()
        try:
            summary = extract_payment_summary(report_date, result.data)
            reset = apply_summary(session, periods[report_date], summary, now=now)
            session.flush()
            savepoint.commit()
            outcome.periods.append(PeriodOutcome(report_date, "reset" if reset else "written"))
        except Exception as exc:
            savepoint.rollback()
            outcome.periods.append(PeriodOutcome(report_date, "error", _error_code(exc)))


def sync_recon_payouts(
    session: Session,
    *,
    call: WalmartCall,
    store_codes: Mapping[str, str],
    source_account_ref: str = SOURCE_REF,
    now: datetime | None = None,
    refresh_existing: bool = False,
    commit_each_store: bool = True,
) -> ReconPayoutSyncResult:
    """store_codes: 领星 store_id → 沃尔玛店铺编码（reviewed_store_id_map）。

    每店结束后单独提交。可用日期拉不到 / 限流 → 这家店记错误停止，已落的 RAW 和已写的期保留，
    其他店照常。
    """
    now = now or utc_now()
    result = ReconPayoutSyncResult(started_at=now)
    for store_id, store_code in sorted(store_codes.items(), key=lambda item: item[1]):
        outcome = StoreOutcome(store_code=store_code)
        result.stores.append(outcome)
        try:
            _sync_store(
                session,
                call=call,
                store_id=store_id,
                store_code=store_code,
                source_account_ref=source_account_ref,
                now=now,
                refresh_existing=refresh_existing,
                outcome=outcome,
            )
        except Exception as exc:
            outcome.error = _error_code(exc)
        if commit_each_store:
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                outcome.error = outcome.error or f"COMMIT_FAILED:{type(exc).__name__}"
                outcome.periods = [p for p in outcome.periods if p.status == "error"]
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
