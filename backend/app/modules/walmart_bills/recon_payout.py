"""从沃尔玛对账报表取每期打款额（纯函数部分，不连库、不调接口）。

接口（V4 通用通道，只读 GET，只允许这两个路径）：
- GET /v3/report/reconreport/availableReconFiles?reportVersion=v1
  → {"availableApReportDates": ["MMDDYYYY", …]}
- GET /v3/report/reconreport/reconFileJson?reportDate=MMDDYYYY&offset=0&noOfRecords=100
  → {"reportData": [行…], "nextOffset", "totalRecords", "description"}；
  行里 "Transaction Type" == "PaymentSummary" 的那一行给本期打款：
  "Total Payable"、"Period Start Date" / "Period End Date"（MM/DD/YYYY）、
  "Transaction Posted Timestamp"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

RECON_DATES_PATH: Final = "/v3/report/reconreport/availableReconFiles"
RECON_FILE_PATH: Final = "/v3/report/reconreport/reconFileJson"
RECON_PAGE_SIZE: Final = 100
ALLOWED_PATHS: Final = frozenset({RECON_DATES_PATH, RECON_FILE_PATH})

SUMMARY_TYPE: Final = "PaymentSummary"
_DATE_8 = re.compile(r"^(\d{2})(\d{2})(\d{4})$")
_DATE_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
# 账户级交易行只保留这些字段，不存商品、地址、订单号
_ACCOUNT_ROW_KEYS: Final = (
    "Transaction Type",
    "Transaction Description",
    "Transaction Reason Description",
    "Amount",
    "Amount Type",
    "Transaction Posted Timestamp",
    "Period Start Date",
    "Period End Date",
    "Transaction Key",
)


class ReconPayoutError(RuntimeError):
    """args[0] 是稳定错误码。"""


@dataclass(frozen=True, slots=True)
class PaymentSummary:
    report_date: date
    total_payable: Decimal
    currency_code: str | None
    period_start_date: date | None
    period_end_date: date | None
    posted_date: date | None
    description: str | None
    account_rows: list[dict[str, Any]] = field(default_factory=list)
    page_rows: int = 0
    has_more: bool = False
    summary_row: dict[str, Any] = field(default_factory=dict)


def parse_report_date(value: Any) -> date:
    """可用日期接口给的是 MMDDYYYY。"""
    if not isinstance(value, str):
        raise ReconPayoutError("WALMART_RECON_DATE_INVALID")
    match = _DATE_8.match(value.strip())
    if match is None:
        raise ReconPayoutError("WALMART_RECON_DATE_INVALID")
    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        raise ReconPayoutError("WALMART_RECON_DATE_INVALID") from None


def report_date_param(value: date) -> str:
    return value.strftime("%m%d%Y")


def parse_available_dates(payload: Any) -> list[date]:
    if not isinstance(payload, dict) or not isinstance(payload.get("availableApReportDates"), list):
        raise ReconPayoutError("WALMART_RECON_DATES_INVALID")
    return sorted({parse_report_date(item) for item in payload["availableApReportDates"]})


def _slash_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    match = _DATE_SLASH.match(value.strip())
    if match is None:
        return None
    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def extract_payment_summary(report_date: date, payload: Any) -> PaymentSummary:
    """从对账报表第一页取 PaymentSummary；没有或不止一行都算报表形状不对。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("reportData"), list):
        raise ReconPayoutError("WALMART_RECON_REPORT_INVALID")
    rows = [row for row in payload["reportData"] if isinstance(row, dict)]
    summaries = [row for row in rows if row.get("Transaction Type") == SUMMARY_TYPE]
    if len(summaries) != 1:
        raise ReconPayoutError("WALMART_RECON_SUMMARY_MISSING")
    summary = summaries[0]
    total = _decimal(summary.get("Total Payable"))
    if total is None:
        raise ReconPayoutError("WALMART_RECON_SUMMARY_MISSING")
    account_rows = [
        {key: row.get(key) for key in _ACCOUNT_ROW_KEYS if not _blank(row.get(key))}
        for row in rows
        if row.get("Transaction Type") != SUMMARY_TYPE
        and _blank(row.get("Customer Order #"))
        and _blank(row.get("Purchase Order #"))
        and _blank(row.get("Partner GTIN"))
    ]
    next_offset = payload.get("nextOffset")
    has_more = isinstance(next_offset, int) and next_offset > 0 and len(rows) >= RECON_PAGE_SIZE
    currency = summary.get("Currency")
    return PaymentSummary(
        report_date=report_date,
        total_payable=total,
        currency_code=currency.strip() if isinstance(currency, str) and currency.strip() else None,
        period_start_date=_slash_date(summary.get("Period Start Date")),
        period_end_date=_slash_date(summary.get("Period End Date")),
        posted_date=_slash_date(summary.get("Transaction Posted Timestamp")),
        description=summary.get("Transaction Description")
        if isinstance(summary.get("Transaction Description"), str)
        else None,
        account_rows=account_rows,
        page_rows=len(rows),
        has_more=has_more,
        summary_row={key: value for key, value in summary.items() if not _blank(value)},
    )


def account_rows_note(rows: list[dict[str, Any]]) -> str:
    """给页面看的一句话：账户级交易各多少（如「Release Reserve +1 行」）。"""
    counts: dict[str, int] = {}
    for row in rows:
        kind = str(row.get("Transaction Type") or "（空）")
        counts[kind] = counts.get(kind, 0) + 1
    return "、".join(f"{kind} {count} 行" for kind, count in sorted(counts.items()))


def lingxing_payable(row: Any) -> Decimal:
    """领星口径的应付：账单总额（有给时）否则明细合计；periods.refresh_periods 同一规则。"""
    stated = getattr(row, "total_payable", None)
    return stated if stated is not None else row.amount_sum


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
