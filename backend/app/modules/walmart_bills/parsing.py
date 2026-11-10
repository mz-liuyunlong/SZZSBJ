"""领星沃尔玛账单（statement/list）响应解析：纯函数，不碰数据库。

响应：{"code": 0, "data": {"list": [...], "totalCount": N, "totalSum": {...}}}。
金额按字符串转 Decimal，不经浮点运算；任何一行不合法就整页失败（不把半截数据当成功）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import JsonValue

# 收货地址类字段永不进业务层（数据源决策 §5）。
DROPPED_FIELDS = frozenset({"shipToCity", "shipToState", "shipToZipcode", "shipToCountry"})

# 已经拆成独立列的字段，不再重复放进 extra_fields。
MAPPED_FIELDS = frozenset(
    {
        "id",
        "storeId",
        "storeName",
        "companyId",
        "reportKey",
        "reportId",
        "reportDate",
        "periodStartDate",
        "periodEndDate",
        "transactionPostedTimestamp",
        "transactionKey",
        "transactionType",
        "transactionDescription",
        "transactionReasonDescription",
        "amountType",
        "amount",
        "currency",
        "totalPayable",
        "shipQty",
        "customerOrderNo",
        "customerOrderLineNo",
        "purchaseOrderNo",
        "purchaseOrderLineNo",
        "partnerItemId",
        "partnerGtin",
        "fulfillmentType",
        "uniqueNo",
        "deleteFlag",
    }
)


class BillRowError(ValueError):
    """一行不合法；code 是固定错误码，不带领星原文。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class BillPage:
    rows: list[dict[str, Any]]
    total_count: int


def provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    return str(value) if isinstance(value, (int, str)) and not isinstance(value, bool) else None


def bill_page(payload: JsonValue) -> BillPage | None:
    """取出这一页的明细和总条数；结构不对返回 None。data.list 为 null 当作空页。"""
    if not isinstance(payload, dict) or provider_code(payload) != "0":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    rows = data.get("list")
    if rows is None:
        rows = []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    total = data.get("totalCount")
    if isinstance(total, bool) or not isinstance(total, (int, str)):
        return None
    try:
        total_count = int(total)
    except ValueError:
        return None
    if total_count < 0:
        return None
    return BillPage(rows=rows, total_count=total_count)


def _text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    text = str(value).strip()
    return text[:limit] if text else None


def _identifier(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    text = str(value).strip()
    if not text.isdigit() or len(text) > 32:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    return text


def _decimal(value: object, *, required: bool) -> Decimal | None:
    if value is None or value == "":
        if required:
            raise BillRowError("SYNC_WALMART_BILL_INVALID_AMOUNT")
        return None
    if isinstance(value, bool):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_AMOUNT")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_AMOUNT") from exc
    if not parsed.is_finite() or abs(parsed) >= Decimal("100000000000000"):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_AMOUNT")
    return parsed.quantize(Decimal("0.0001"))


def _date(value: object, *, required: bool) -> date | None:
    if value is None or value == "":
        if required:
            raise BillRowError("SYNC_WALMART_BILL_INVALID_DATE")
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_DATE") from exc


def _posted(value: object) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_DATE") from exc
    if parsed.tzinfo is not None:
        # 领星给的是不带时区的本地时间；带了时区说明口径变了，不猜。
        raise BillRowError("SYNC_WALMART_BILL_INVALID_DATE")
    return parsed


def _int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW") from exc


def _clean(value: object) -> object:
    """extra_fields 只放 JSON 安全的值；浮点转成字符串，避免精度丢失。"""
    if isinstance(value, float):
        return str(Decimal(str(value)))
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return json.loads(json.dumps(value, default=str))


# 行身份用的字段（数据源决策 §3.1）：领星行号本身不保证一行一个（同一订单行多种金额类型、
# 同金额重复出现都见过），所以用组合键，同组合键再按出现顺序编号。
IDENTITY_FIELDS = (
    "id",
    "reportKey",
    "transactionKey",
    "transactionPostedTimestamp",
    "customerOrderNo",
    "customerOrderLineNo",
    "amountType",
    "transactionDescription",
    "amount",
)


def identity_base(row: dict[str, Any]) -> str:
    """组合键的摘要；同一时间段里撞上的再由调用方加出现序号。"""
    parts = [
        str(_clean(row.get(name)) if row.get(name) is not None else "") for name in IDENTITY_FIELDS
    ]
    encoded = "\x1f".join(parts)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def line_key(base: str, ordinal: int) -> str:
    return hashlib.sha256(f"{base}:{ordinal}".encode()).hexdigest()


def row_hash(row: dict[str, Any]) -> str:
    kept = {key: _clean(value) for key, value in row.items() if key not in DROPPED_FIELDS}
    encoded = json.dumps(kept, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_bill_row(
    row: dict[str, Any],
    *,
    expected_store_id: str,
    window_start: date,
    window_end: date,
) -> dict[str, Any]:
    """把一行领星账单明细转成明细表的列。

    - 店铺对不上、交易日期不在请求的时间段里，都按错误处理：说明接口的筛选口径变了，
      这时整次同步失败，不覆盖已有数据。
    """
    store_id = _identifier(row.get("storeId"))
    if store_id != expected_store_id:
        raise BillRowError("SYNC_WALMART_BILL_STORE_MISMATCH")
    posted_at = _posted(row.get("transactionPostedTimestamp"))
    posted_date = posted_at.date()
    if not window_start <= posted_date <= window_end:
        raise BillRowError("SYNC_WALMART_BILL_DATE_OUT_OF_WINDOW")
    report_key = _text(row.get("reportKey"), 64)
    if report_key is None:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    delete_flag = _int(row.get("deleteFlag")) or 0
    if delete_flag not in (0, 1):
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    currency = _text(row.get("currency"), 8)
    if currency is None:
        raise BillRowError("SYNC_WALMART_BILL_INVALID_ROW")
    report_id = row.get("reportId")
    return {
        "store_id": store_id,
        "lx_line_id": _identifier(row.get("id")),
        "report_key": report_key,
        "report_id": None if report_id in (None, "") else _identifier(report_id),
        "report_date": _date(row.get("reportDate"), required=True),
        "period_start_date": _date(row.get("periodStartDate"), required=False),
        "period_end_date": _date(row.get("periodEndDate"), required=False),
        "posted_at": posted_at,
        "posted_date": posted_date,
        "transaction_key": _text(row.get("transactionKey"), 128),
        "transaction_type": _text(row.get("transactionType"), 128),
        "transaction_description": _text(row.get("transactionDescription"), 2000),
        "transaction_reason_description": _text(row.get("transactionReasonDescription"), 2000),
        "amount_type": _text(row.get("amountType"), 128),
        "amount": _decimal(row.get("amount"), required=True),
        "currency_code": currency.upper(),
        "total_payable": _decimal(row.get("totalPayable"), required=False),
        "ship_qty": _int(row.get("shipQty")),
        "customer_order_no": _text(row.get("customerOrderNo"), 64),
        "customer_order_line_no": _text(row.get("customerOrderLineNo"), 32),
        "purchase_order_no": _text(row.get("purchaseOrderNo"), 64),
        "purchase_order_line_no": _text(row.get("purchaseOrderLineNo"), 32),
        "partner_item_id": _text(row.get("partnerItemId"), 64),
        "partner_gtin": _text(row.get("partnerGtin"), 32),
        "fulfillment_type": _text(row.get("fulfillmentType"), 64),
        "unique_no": _text(row.get("uniqueNo"), 64),
        "delete_flag": delete_flag,
        "extra_fields": {
            key: _clean(value)
            for key, value in row.items()
            if key not in MAPPED_FIELDS and key not in DROPPED_FIELDS
        },
        "row_hash": row_hash(row),
        "identity_base": identity_base(row),
    }
