# ruff: noqa: E501, E402, UP031
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ParsedRow:
    """解析器输出（未标准化）：字段全是来源原文字符串。"""

    account_key: str
    date_raw: str
    time_raw: str
    source_timezone: str
    amount_raw: str
    currency: str
    balance_raw: str | None
    counterparty_name: str
    counterparty_account_raw: str
    description_raw: str
    memo_raw: str
    source_ref_full: str
    statement_row_no: int
    local_dt: dt.datetime | None = None  # 解析器已拿到完整日期时间时直接给


@dataclass
class Line:
    """标准化流水（对应 std_finance_cashflow_lines 一行，入库前）。"""

    account_key: str
    business_date: dt.date
    source_time_utc: dt.datetime | None
    source_timezone: str
    source_time_raw: str
    amount: Decimal
    currency_code: str
    balance_after: Decimal | None
    counterparty_name: str
    counterparty_account_last4: str
    description: str  # 脱敏后（入库 / 展示）
    memo: str  # 脱敏后
    description_raw: str  # 脱敏前原文（只用于指纹，不入库）
    source_ref: str  # 后 10 位（入库）
    source_ref_full: str  # 全值（只用于指纹，不入库）
    statement_row_no: int
    file_row_order: int = 0
    dup_ordinal: int = 1
    line_uid: str = ""


@dataclass
class FileResult:
    file_name: str
    sha256: str
    status: str  # parsed / rejected / duplicate_file
    file_id: int | None = None
    account_keys: list = field(default_factory=list)
    note: str = ""
    reject_reason: str = ""
    rows_parsed: int = 0
    rows_new: int = 0
    rows_duplicate: int = 0
    balance_chain_ok: bool | None = None
    declared_range: tuple | None = None
    warnings: list = field(default_factory=list)


class RejectFile(Exception):
    """整个文件拒绝（按文件原子）：消息是给财务看的中文原因。"""
