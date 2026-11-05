# ruff: noqa: E501, E402, UP031
"""金额 / 时间 / 脱敏。金额全链路 Decimal，float 一律拒绝（xls 数值在读取层就转成字符串）。"""

from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .model import Line, ParsedRow, RejectFile

SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = dt.UTC
Q4 = Decimal("0.0001")
EXCEL_EPOCH = dt.datetime(1899, 12, 30)

# ---------------------------------------------------------------- 金额


def to_decimal(value) -> Decimal | None:
    """来源文本 → Decimal(4 位)。不接受 float（防止二进制误差进入金额）。"""
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("金额不允许以 float 进入：请在读取层转为字符串")
    if isinstance(value, (int, Decimal)):
        d = Decimal(value)
    else:
        s = str(value).strip()
        for ch in (",", "，", "¥", "$", " "):
            s = s.replace(ch, "")
        if s in ("", "-", "/", "--"):
            return None
        try:
            d = Decimal(s)
        except InvalidOperation as exc:
            raise RejectFile("金额无法解析：%s" % s[:24]) from exc
    if not d.is_finite():
        raise RejectFile("金额不是有限数")
    return d.quantize(Q4, rounding=ROUND_HALF_UP)


def fmt_amount(d: Decimal | None) -> str:
    return "" if d is None else format(d.quantize(Q4, rounding=ROUND_HALF_UP), "f")


# ---------------------------------------------------------------- 时间

_TZ_ALIASES = {"UTC": "UTC", "GMT": "UTC", "Z": "UTC", "UTC+0": "UTC", "UTC+00:00": "UTC"}


def resolve_tz(name: str):
    n = (name or "").strip()
    if n.upper() in _TZ_ALIASES:
        return UTC
    try:
        return ZoneInfo(n)
    except Exception as exc:  # noqa: BLE001
        raise RejectFile("时区无法识别：%s" % n[:20]) from exc


def excel_serial_to_datetime(s: str) -> dt.datetime:
    d = Decimal(s)
    days = int(d)
    secs = int(((d - days) * 86400).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return EXCEL_EPOCH + dt.timedelta(days=days, seconds=secs)


_DT_PATTERNS = (
    (
        re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$"),
        "ymd",
    ),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "ymd"),
    (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "mdy"),  # MM-DD-YYYY
)


def parse_local_datetime(date_raw: str, time_raw: str) -> dt.datetime:
    s = (date_raw or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", s) and len(s.split(".")[0]) <= 6:  # Excel 序列日期
        base = excel_serial_to_datetime(s)
        d, t = base.date(), base.time()
    else:
        d = t = None
        for rx, order in _DT_PATTERNS:
            m = rx.match(s)
            if not m:
                continue
            g = m.groups()
            if order == "ymd":
                d = dt.date(int(g[0]), int(g[1]), int(g[2]))
                if len(g) > 3 and g[3]:
                    t = dt.time(int(g[3]), int(g[4]), int(g[5] or 0))
            else:
                d = dt.date(int(g[2]), int(g[0]), int(g[1]))
            break
        if d is None:
            raise RejectFile("日期无法解析：%s" % s[:20])
    tr = (time_raw or "").strip()
    if tr:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", tr)
        if not m:
            raise RejectFile("时间无法解析：%s" % tr[:12])
        t = dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    return dt.datetime.combine(d, t or dt.time(0, 0, 0))


def to_utc(local: dt.datetime, tz_name: str) -> dt.datetime:
    tz = resolve_tz(tz_name)
    return local.replace(tzinfo=tz).astimezone(UTC)


# ---------------------------------------------------------------- 脱敏

ID_CARD = re.compile(
    r"(?<![0-9])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])"
)
LONG_DIGITS = re.compile(r"(?<!\d)\d{16,}(?!\d)")
EMAIL = re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)")


def mask_text(s: str) -> str:
    s = ID_CARD.sub("[证件号已剔除]", s or "")
    s = LONG_DIGITS.sub(lambda m: "…" + m.group(0)[-4:], s)
    return EMAIL.sub(r"\1…@\2", s)


def last4(s: str) -> str:
    digits = re.sub(r"\D", "", re.sub(r"\.0$", "", s or ""))
    return digits[-4:]


# ---------------------------------------------------------------- 标准化


def normalize(row: ParsedRow) -> Line:
    if row.local_dt is not None:
        local = row.local_dt
    else:
        local = parse_local_datetime(row.date_raw, row.time_raw)
    utc = to_utc(local, row.source_timezone)
    amount = to_decimal(row.amount_raw)
    if amount is None:
        raise RejectFile("第 %d 行没有金额" % row.statement_row_no)
    return Line(
        account_key=row.account_key,
        business_date=utc.astimezone(
            SHANGHAI
        ).date(),  # 财务流水业务日 = Asia/Shanghai（规则 §7 例外）
        source_time_utc=utc,
        source_timezone=row.source_timezone,
        source_time_raw=("%s %s" % (row.date_raw, row.time_raw)).strip(),
        amount=amount,
        currency_code=row.currency,
        balance_after=to_decimal(row.balance_raw),
        counterparty_name=mask_text(row.counterparty_name),
        counterparty_account_last4=last4(row.counterparty_account_raw),
        description=mask_text(row.description_raw),
        memo=mask_text(row.memo_raw),
        description_raw=row.description_raw,
        source_ref=(row.source_ref_full or "")[-10:],
        source_ref_full=row.source_ref_full or "",
        statement_row_no=row.statement_row_no,
    )
