"""WFS 费用报表解析：三种来源，只认内容不认文件名。

- 结算报表（SETTLEMENT）：接口下载的（Order ID / PO Number / WFS Reference ID /
  Transaction Date and Time / GTIN / Net Payable …）和卖家后台「服务费 → 下载」的
  （Walmart.com PO # / WFSReferenceID / Transaction Date/Time / Partner GTIN …）两种列名，
  同一套字段。配送费（FulfillmentFee）行不入表（Rocky 11-12），其余类型都收。
- 仓储费报表（WFS_STORAGE_FEE）：接口下载的只有明细表头（账期由调用方给）；
  卖家后台下载的多一段汇总块（Report start date / Report end date / Total storage fees），
  有就用它定账期并做守恒校验。新旧两版表头都认。
- 入库运输报告：ReportingPeriod_StartDate / EndDate 两行 + 明细（Shipment ID / Delivery Date /
  Service Type / Reason Code / Actual Charge …）；按货件汇总。

金额一律转成「我方视角」：正 = Walmart 付我们，负 = 扣费。
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Final

FEE_SOURCE_SETTLEMENT = "settlement"
FEE_SOURCE_STORAGE = "storage"
FEE_SOURCE_INBOUND = "inbound"

FULFILLMENT_FEE = "FulfillmentFee"
STORAGE_FEE = "StorageFee"
INBOUND_FEE = "InboundTransportationFee"
RETURN_PROCESSING_FEE = "ReturnProcessingFee"
# 结算报表里这两类另有专门报表（仓储按 GTIN、入库按货件），店铺级的周汇总行不入表，只用于核对
SETTLEMENT_SKIP = frozenset({FULFILLMENT_FEE, STORAGE_FEE, INBOUND_FEE})

MAX_BYTES = 16 * 1024 * 1024


class ParseError(ValueError):
    """文件不是我们认识的报表，或内容不合规；message 给财务看。"""


@dataclass
class ParsedLine:
    fee_type: str
    transaction_date: date
    amount_usd: Decimal  # 我方视角
    line_key: str
    source_ref: str = ""
    reason_code: str = ""
    detail: str = ""
    po_number: str = ""
    partner_id: str = ""
    gtin: str = ""
    item_id: str = ""
    sku: str = ""
    quantity: Decimal | None = None
    original_amount: Decimal | None = None
    discount_savings: Decimal | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class ParsedReport:
    fee_source: str
    lines: list[ParsedLine]
    period_start: date | None = None
    period_end: date | None = None
    declared_total: Decimal | None = None
    partner_id: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 工具


def _clean(value: str | None) -> str:
    """去掉 Excel 保护符 ="…" 和首尾引号 / 空白。"""
    text = (value or "").strip()
    text = re.sub(r'^="?', "", text)
    return text.strip('"').strip()


def _decimal(value: str | None) -> Decimal | None:
    text = _clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"金额不是数字：{text[:20]}") from exc


def _date(value: str | None) -> date | None:
    text = _clean(value)[:10]
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"日期格式不认识：{text}")


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", _clean(value))


def _rows(content: bytes) -> list[list[str]]:
    if len(content) > MAX_BYTES:
        raise ParseError("文件超过 16MB，请确认是单店铺报表")
    text = content.decode("utf-8-sig", errors="replace")
    # newline="" 让 csv 自己处理 \r\n / \r（卖家后台导出有旧 Mac 换行的情况）
    try:
        return list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ParseError(f"CSV 格式读不出来：{exc}") from exc


def _header_index(header: list[str], *names: str) -> int:
    cleaned = [_clean(cell) for cell in header]
    for name in names:
        if name in cleaned:
            return cleaned.index(name)
    return -1


def _header_regex(header: list[str], pattern: str) -> int:
    rx = re.compile(pattern)
    for index, cell in enumerate(header):
        if rx.fullmatch(_clean(cell)):
            return index
    return -1


def friday_of(day: date) -> date:
    """Walmart 账单周 = 周六～周五；扣费日期（Date charged）取当周周五。"""
    return day + timedelta(days=(4 - day.weekday()) % 7)


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:64]


def detect(content: bytes) -> str:
    """按内容判断是哪种报表；认不出来抛 ParseError。"""
    rows = _rows(content)
    for row in rows[:40]:
        cleaned = [_clean(cell) for cell in row]
        if "Transaction Type" in cleaned and ("Net Payable" in cleaned):
            return FEE_SOURCE_SETTLEMENT
        if cleaned[:2] == ["GTIN", "SKU"] or ("GTIN" in cleaned and "Final storage fee" in cleaned):
            return FEE_SOURCE_STORAGE
        if cleaned[:2] == ["Shipment ID", "Delivery Date"] or cleaned[:1] == [
            "ReportingPeriod_StartDate"
        ]:
            return FEE_SOURCE_INBOUND
    raise ParseError(
        "认不出报表类型：要结算报表、仓储费报表或入库运输报告的原始 CSV（配送费报表不入这张表）"
    )


ZIP_MAX_MEMBERS: Final = 50
ZIP_MAX_MEMBER_BYTES: Final = 16 * 1024 * 1024
ZIP_MAX_TOTAL_BYTES: Final = 64 * 1024 * 1024


def expand_upload(file_name: str, content: bytes) -> list[tuple[str, bytes]]:
    """卖家后台下载的报表常是 ZIP：解开取里面的 CSV，每个 CSV 单独导入；不是 ZIP 原样返回。

    只取 .csv，跳过目录、__MACOSX 和隐藏文件；限制个数和解压后大小，防压缩炸弹。
    """
    if not content.startswith(b"PK"):
        return [(file_name, content)]
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ParseError("ZIP 文件损坏，打不开") from exc
    members = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and not info.filename.rsplit("/", 1)[-1].startswith(".")
        and info.filename.lower().endswith(".csv")
    ]
    if not members:
        raise ParseError("ZIP 里没有 CSV 文件")
    if len(members) > ZIP_MAX_MEMBERS:
        raise ParseError(f"ZIP 里的 CSV 超过 {ZIP_MAX_MEMBERS} 个，请分开上传")
    total = 0
    out: list[tuple[str, bytes]] = []
    for info in members:
        if info.file_size > ZIP_MAX_MEMBER_BYTES:
            raise ParseError(f"ZIP 里的 {info.filename} 解压后超过 16MB")
        data = archive.read(info)[: ZIP_MAX_MEMBER_BYTES + 1]
        if len(data) > ZIP_MAX_MEMBER_BYTES:
            raise ParseError(f"ZIP 里的 {info.filename} 解压后超过 16MB")
        total += len(data)
        if total > ZIP_MAX_TOTAL_BYTES:
            raise ParseError("ZIP 解压后合计超过 64MB，请分开上传")
        out.append((f"{file_name}/{info.filename.rsplit('/', 1)[-1]}", data))
    return out


# ---------------------------------------------------------------- 结算报表


SETTLEMENT_COLUMNS = {
    "type": ("Transaction Type",),
    "reason": ("Reason Code",),
    "detail": ("Detail",),
    "ref": ("WFS Reference ID", "WFSReferenceID"),
    "date": ("Transaction Date and Time", "Transaction Date/Time"),
    "qty": ("Quantity", "Qty"),
    "partner": ("Partner ID",),
    "gtin": ("GTIN", "Partner GTIN"),
    "po": ("PO Number", "Walmart.com PO #"),
    "order": ("Order ID", "Walmart.com Order #"),
    "net": ("Net Payable",),
    "orig": ("Original Amount",),
    "disc": ("Discount Savings",),
}


def parse_settlement(content: bytes) -> ParsedReport:
    rows = _rows(content)
    head_at = next(
        (i for i, row in enumerate(rows) if _header_index(row, "Transaction Type") >= 0), -1
    )
    if head_at < 0:
        raise ParseError("结算报表缺少表头（Transaction Type）")
    header = rows[head_at]
    col = {name: _header_index(header, *names) for name, names in SETTLEMENT_COLUMNS.items()}
    for required in ("type", "date", "net"):
        if col[required] < 0:
            raise ParseError(f"结算报表缺列：{SETTLEMENT_COLUMNS[required][0]}")

    def cell(row: list[str], name: str) -> str:
        index = col[name]
        return _clean(row[index]) if 0 <= index < len(row) else ""

    lines: list[ParsedLine] = []
    partner = ""
    seen: set[str] = set()
    skipped: dict[str, int] = {}
    for row in rows[head_at + 1 :]:
        if not any(_clean(c) for c in row):
            continue
        fee_type = cell(row, "type")
        if not fee_type:
            continue
        # Partner ID 每行都一样；不入表的汇总行也取，只有汇总行的文件也能认店
        partner = partner or _digits(cell(row, "partner"))
        if fee_type in SETTLEMENT_SKIP:
            skipped[fee_type] = skipped.get(fee_type, 0) + 1
            continue
        when = _date(cell(row, "date"))
        net = _decimal(cell(row, "net"))
        if when is None or net is None:
            raise ParseError(f"结算报表有一行缺交易日期或金额（{fee_type}）")
        ref = cell(row, "ref")
        gtin = _digits(cell(row, "gtin"))
        reason = cell(row, "reason")
        key = (
            _key("settlement", ref)
            if ref
            else _key(
                "settlement", fee_type, reason, when.isoformat(), str(net), gtin, cell(row, "po")
            )
        )
        if key in seen:
            # 领星确实会返回完全相同的两笔（没有 Reference ID 时）：按出现顺序编号
            ordinal = 2
            while _key(key, str(ordinal)) in seen:
                ordinal += 1
            key = _key(key, str(ordinal))
        seen.add(key)
        partner = partner or _digits(cell(row, "partner"))
        lines.append(
            ParsedLine(
                fee_type=fee_type,
                transaction_date=when,
                amount_usd=-net,
                line_key=key,
                source_ref=ref,
                reason_code=reason,
                detail=cell(row, "detail")[:2000],
                po_number=cell(row, "po")[:64],
                partner_id=_digits(cell(row, "partner")),
                gtin=gtin,
                quantity=_decimal(cell(row, "qty")),
                original_amount=(None if (v := _decimal(cell(row, "orig"))) is None else -v),
                discount_savings=_decimal(cell(row, "disc")),
                extra={"order_id": cell(row, "order")} if cell(row, "order") else {},
            )
        )
    report = ParsedReport(FEE_SOURCE_SETTLEMENT, lines, partner_id=partner)
    if lines:
        report.period_start = min(line.transaction_date for line in lines)
        report.period_end = max(line.transaction_date for line in lines)
    if skipped:
        names = {
            "FulfillmentFee": "配送费",
            "StorageFee": "仓储费店铺周汇总",
            "InboundTransportationFee": "入库运费店铺周汇总",
        }
        parts = "、".join(f"{names.get(k, k)} {v} 行" for k, v in sorted(skipped.items()))
        report.warnings.append(
            f"{parts}不入表（仓储费、入库运费按商品要导 WFS 报告里的仓储 / 入库运输报告）"
        )
    return report


# ---------------------------------------------------------------- 仓储费报表


def parse_storage(
    content: bytes, *, period_start: date | None = None, period_end: date | None = None
) -> ParsedReport:
    rows = _rows(content)
    summary_at = next(
        (i for i, row in enumerate(rows) if _clean(row[0] if row else "") == "Report start date"),
        -1,
    )
    head_at = next(
        (
            i
            for i, row in enumerate(rows)
            if _header_index(row, "GTIN") >= 0 and _header_index(row, "SKU") >= 0
        ),
        -1,
    )
    if head_at < 0:
        raise ParseError("仓储费报表缺少明细表头（GTIN, SKU）")
    declared: Decimal | None = None
    if summary_at >= 0 and summary_at + 1 < len(rows):
        summary = [_clean(c) for c in rows[summary_at + 1]]
        period_start = _date(summary[0] if summary else "") or period_start
        period_end = _date(summary[1] if len(summary) > 1 else "") or period_end
        declared = _decimal(summary[2] if len(summary) > 2 else "")
    if period_start is None or period_end is None:
        raise ParseError("仓储费报表没有汇总块（Report start date），请选择账期后再导入")
    if period_start > period_end:
        raise ParseError(f"仓储费账期异常：{period_start} ~ {period_end}")
    header = rows[head_at]
    idx = {
        "gtin": _header_index(header, "GTIN"),
        "sku": _header_index(header, "SKU"),
        "item": _header_index(header, "Item ID"),
        "days": _header_index(header, "Days in report period"),
        "final": _header_index(header, "Final storage fee"),
        "orig": _header_index(header, "Original Amount"),
        "disc": _header_index(header, "Discount Savings"),
        "avg_std": _header_regex(header, r"Standard: average (daily )?units available"),
        "avg_lt1": _header_regex(
            header, r"Long-term \(366-450( days)?\): average (daily )?units available"
        ),
        "avg_lt2": _header_regex(
            header, r"Long-term \((451\+|450\+)( days)?\): average (daily )?units available"
        ),
    }
    if idx["final"] < 0:
        raise ParseError("仓储费报表缺列：Final storage fee（版式可能已变）")

    def cell(row: list[str], name: str) -> str:
        index = idx[name]
        return _clean(row[index]) if 0 <= index < len(row) else ""

    lines: list[ParsedLine] = []
    for row in rows[head_at + 1 :]:
        gtin = _digits(cell(row, "gtin"))
        if len(gtin) < 8:
            continue  # 说明行 / 杂行
        final = _decimal(cell(row, "final")) or Decimal("0")
        orig = _decimal(cell(row, "orig"))
        lines.append(
            ParsedLine(
                fee_type=STORAGE_FEE,
                transaction_date=period_end,
                amount_usd=-final,
                line_key=_key("storage", gtin, period_start.isoformat(), period_end.isoformat()),
                gtin=gtin,
                item_id=_digits(cell(row, "item")),
                sku=cell(row, "sku"),
                quantity=_decimal(cell(row, "avg_std")),
                original_amount=None if orig is None else -orig,
                discount_savings=_decimal(cell(row, "disc")),
                extra={
                    "days": cell(row, "days"),
                    "avg_long_term": str(
                        (_decimal(cell(row, "avg_lt1")) or 0)
                        + (_decimal(cell(row, "avg_lt2")) or 0)
                    ),
                },
            )
        )
    total = sum((-line.amount_usd for line in lines), Decimal("0"))
    if lines and declared is not None and abs(total - declared) > Decimal("0.5"):
        raise ParseError(
            f"守恒不平，整份拒收：明细合计 {total:.2f} vs 报表头部 Total {declared:.2f}"
        )
    return ParsedReport(
        FEE_SOURCE_STORAGE,
        lines,
        period_start,
        period_end,
        declared if declared is not None else total,
    )


# ---------------------------------------------------------------- 入库运输报告


SHIPMENT_ID = re.compile(r"^[0-9A-Z]{5,20}$")


def parse_inbound(content: bytes) -> ParsedReport:
    rows = _rows(content)
    period_at = next(
        (
            i
            for i, row in enumerate(rows)
            if _clean(row[0] if row else "") == "ReportingPeriod_StartDate"
        ),
        -1,
    )
    head_at = next(
        (
            i
            for i, row in enumerate(rows)
            if _clean(row[0] if row else "") == "Shipment ID"
            and _clean(row[1] if len(row) > 1 else "") == "Delivery Date"
        ),
        -1,
    )
    if period_at < 0 or head_at < 0:
        raise ParseError(
            "入库运输报告缺少 ReportingPeriod 头或明细表头（Shipment ID, Delivery Date）"
        )
    period = [_clean(c) for c in rows[period_at + 1]] if period_at + 1 < len(rows) else []
    period_start = _date(period[0] if period else "")
    period_end = _date(period[1] if len(period) > 1 else "")
    if period_start is None or period_end is None or period_start > period_end:
        raise ParseError("入库运输报告账期异常")
    header = rows[head_at]
    idx = {
        "cargo": _header_index(header, "Shipment ID"),
        "date": _header_index(header, "Delivery Date"),
        "service": _header_index(header, "Service Type"),
        "reason": _header_index(header, "Reason Code"),
        "charge": _header_index(header, "Actual Charge"),
    }
    if idx["charge"] < 0:
        raise ParseError("入库运输报告缺列：Actual Charge（版式可能已变）")

    def cell(row: list[str], name: str) -> str:
        index = idx[name]
        return _clean(row[index]) if 0 <= index < len(row) else ""

    by_cargo: dict[str, dict[str, object]] = {}
    for row in rows[head_at + 1 :]:
        cargo = cell(row, "cargo").upper()
        if not SHIPMENT_ID.fullmatch(cargo) or not re.search(r"\d", cargo):
            continue
        charge = _decimal(cell(row, "charge")) or Decimal("0")
        entry = by_cargo.setdefault(
            cargo,
            {"amount": Decimal("0"), "rows": 0, "services": set(), "reasons": set(), "date": None},
        )
        entry["amount"] = entry["amount"] + charge  # type: ignore[operator]
        entry["rows"] = entry["rows"] + 1  # type: ignore[operator]
        if cell(row, "service"):
            entry["services"].add(cell(row, "service"))  # type: ignore[union-attr]
        if cell(row, "reason"):
            entry["reasons"].add(cell(row, "reason"))  # type: ignore[union-attr]
        delivered = _date(cell(row, "date"))
        if delivered and (entry["date"] is None or delivered < entry["date"]):  # type: ignore[operator]
            entry["date"] = delivered
    lines = [
        ParsedLine(
            fee_type=INBOUND_FEE,
            transaction_date=entry["date"] or period_end,  # type: ignore[arg-type]
            amount_usd=-entry["amount"],  # type: ignore[operator]
            line_key=_key("inbound", cargo, period_start.isoformat(), period_end.isoformat()),
            source_ref=cargo,
            po_number=cargo,
            reason_code="、".join(sorted(entry["reasons"]))[:128],  # type: ignore[arg-type]
            detail="、".join(sorted(entry["services"]))[:2000],  # type: ignore[arg-type]
            extra={"rows": entry["rows"]},
        )
        for cargo, entry in by_cargo.items()
    ]
    total = sum((-line.amount_usd for line in lines), Decimal("0"))
    return ParsedReport(FEE_SOURCE_INBOUND, lines, period_start, period_end, total)


def parse(
    content: bytes,
    *,
    fee_source: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ParsedReport:
    source = fee_source or detect(content)
    if source == FEE_SOURCE_SETTLEMENT:
        return parse_settlement(content)
    if source == FEE_SOURCE_STORAGE:
        return parse_storage(content, period_start=period_start, period_end=period_end)
    if source == FEE_SOURCE_INBOUND:
        return parse_inbound(content)
    raise ParseError(f"不认识的报表类型：{source}")
