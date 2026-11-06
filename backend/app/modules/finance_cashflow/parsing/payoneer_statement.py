# ruff: noqa: E501, UP031
"""派安盈月结明细 CSV（月底才能下载，rocky 11-05）：只用来补提现的实际到账金额，不新增流水。

表头以 Transaction Date,Transaction Time,Time Zone,Transaction ID 开头，比每周交易报告多
Transaction ID、Transfer Amount、Transfer Amount Currency 三列。提现到国内银行 / 个人时，
Transfer Amount 是对方实际到账金额（人民币或美元），派安盈的汇率就是 到账人民币 ÷ 扣款美元。
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal

from . import readers
from .detector import PAYONEER_COLLECTOR, PAYONEER_SELLER
from .model import RejectFile
from .normalize import SHANGHAI, mask_text, resolve_tz, to_decimal
from .pipeline import UNEXPECTED_PARSE_ERRORS as UNEXPECTED_ERRORS
from .readers import cell
from .seed import Seed

__all__ = [
    "UNEXPECTED_ERRORS",
    "ParsedStatement",
    "StatementRow",
    "is_statement",
    "parse_statement",
]

STATEMENT_HEADER = "Transaction Date,Transaction Time,Time Zone,Transaction ID"
PROVIDER = "payoneer_statement"
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
REQUIRED = (
    "Transaction Date",
    "Transaction Time",
    "Time Zone",
    "Transaction ID",
    "Description",
    "Credit Amount",
    "Debit Amount",
    "Currency",
    "Transfer Amount",
    "Transfer Amount Currency",
    "Status",
)


@dataclass(frozen=True)
class StatementRow:
    row_no: int
    txn_id: str
    txn_time_utc: dt.datetime
    business_date: dt.date
    description: str
    amount: Decimal  # 入正出负，账户币种
    currency_code: str
    transfer_amount: Decimal | None
    transfer_currency: str


@dataclass(frozen=True)
class ParsedStatement:
    account_key: str
    note: str
    rows: list[StatementRow]


def is_statement(content: bytes) -> bool:
    try:
        head = content[:200].decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return head.startswith(STATEMENT_HEADER)


def _utc(date_raw: str, time_raw: str, tz_name: str, row_no: int) -> dt.datetime:
    day = DATE_RE.match(date_raw)
    clock = TIME_RE.match(time_raw or "00:00:00")
    if not day or not clock:
        raise RejectFile("第 %d 行日期或时间无法解析" % row_no)
    month, mday, year = (int(x) for x in day.groups())
    local = dt.datetime(
        year, month, mday, int(clock.group(1)), int(clock.group(2)), int(clock.group(3) or 0)
    )
    return local.replace(tzinfo=resolve_tz(tz_name or "UTC")).astimezone(dt.UTC)


def parse_statement(content: bytes, seed: Seed) -> ParsedStatement:
    """按 Description 判断是卖家户还是归集户（和每周交易报告同一套判断），只收 Completed 行。"""
    try:
        rows = readers.read_csv(content)
    except UnicodeDecodeError as exc:
        raise RejectFile("派安盈月结明细不是 UTF-8 CSV") from exc
    if not rows:
        raise RejectFile("派安盈月结明细是空文件")
    head = [cell(x) for x in rows[0]]
    missing = [name for name in REQUIRED if name not in head]
    if missing:
        raise RejectFile("派安盈月结明细缺列：%s" % "、".join(missing))
    ix = {name: head.index(name) for name in REQUIRED}

    def g(row: list[str], key: str) -> str:
        at = ix[key]
        return cell(row[at]) if at < len(row) else ""

    body = [row for row in rows[1:] if any(cell(x) for x in row)]
    seller = sum(1 for row in body if PAYONEER_SELLER.search(g(row, "Description")))
    collector = sum(1 for row in body if PAYONEER_COLLECTOR.search(g(row, "Description")))
    if seller == collector:
        raise RejectFile(
            "派安盈账户无法判定，请人工指定" if seller else "派安盈月结明细里没有可识别的交易描述"
        )
    account = seed.payoneer("seller" if seller > collector else "collector")
    if account is None:
        raise RejectFile("派安盈账户没登记")
    out: list[StatementRow] = []
    for row_no, row in enumerate(rows[1:], start=2):
        if not any(cell(x) for x in row) or g(row, "Status") != "Completed":
            continue
        credit = to_decimal(g(row, "Credit Amount")) or Decimal(0)
        debit = to_decimal(g(row, "Debit Amount")) or Decimal(0)
        amount = credit - debit
        if not amount:
            continue
        utc = _utc(
            g(row, "Transaction Date"), g(row, "Transaction Time"), g(row, "Time Zone"), row_no
        )
        transfer = to_decimal(g(row, "Transfer Amount"))
        out.append(
            StatementRow(
                row_no=row_no,
                txn_id=g(row, "Transaction ID")[:32],
                txn_time_utc=utc,
                business_date=utc.astimezone(SHANGHAI).date(),
                description=mask_text(g(row, "Description")),
                amount=amount,
                currency_code=g(row, "Currency") or "USD",
                transfer_amount=transfer if transfer else None,
                transfer_currency=g(row, "Transfer Amount Currency")[:8] if transfer else "",
            )
        )
    if not out:
        raise RejectFile("派安盈月结明细里没有已完成的交易")
    return ParsedStatement(
        account_key=account.account_key,
        note="派安盈月结补充 · %s（只补实际到账金额，不新增流水）" % account.display_name,
        rows=out,
    )
