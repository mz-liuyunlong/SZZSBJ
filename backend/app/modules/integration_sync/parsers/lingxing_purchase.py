"""Parsers for the three PMC purchase feeds (Gate 2, PR-D).

Each parser turns one raw page (already redacted) into ODS row dicts whose keys match
the ``app.modules.pmc_purchase.models`` columns. Every header keeps its full record in
``payload_json``; extracted columns are copied as delivered (ids and timestamps as
strings, money as ``Decimal``). Structural problems raise ``PurchaseParseError`` with a
stable code; business-quality observations are returned, not raised, so a first
production capture can confirm provider semantics before any threshold becomes fatal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from pydantic import JsonValue

from app.integrations.lingxing.pmc_purchase_contracts import (
    PURCHASE_ORDER_ENDPOINT,
    PURCHASE_PLAN_ENDPOINT,
    RECEIPT_ORDER_ENDPOINT,
    pmc_purchase_provider_code,
    pmc_purchase_response_items,
    pmc_purchase_response_total,
)

PARSER_VERSION: Final = "v1"
PARSER_KEYS: Final[dict[str, str]] = {
    PURCHASE_PLAN_ENDPOINT: "lingxing.pmc_purchase.purchase_plan_list.v1",
    PURCHASE_ORDER_ENDPOINT: "lingxing.pmc_purchase.purchase_order_list.v1",
    RECEIPT_ORDER_ENDPOINT: "lingxing.pmc_purchase.purchase_receipt_order_list.v1",
}
SOURCE_ROOT: Final[dict[str, str]] = {
    PURCHASE_PLAN_ENDPOINT: "$.data",
    PURCHASE_ORDER_ENDPOINT: "$.data",
    RECEIPT_ORDER_ENDPOINT: "$.data.list",
}


class PurchaseParseError(ValueError):
    """Structural parse failure; ``code`` is a stable uppercase identifier."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PurchaseQualityReport:
    """Business-quality observations for one page (informational in Gate 2)."""

    header_line_mismatches: int = 0
    missing_line_keys: int = 0
    non_string_store_ids: int = 0
    receipts_without_purchase_order: int = 0

    def merged(self, other: PurchaseQualityReport) -> PurchaseQualityReport:
        return PurchaseQualityReport(
            header_line_mismatches=self.header_line_mismatches + other.header_line_mismatches,
            missing_line_keys=self.missing_line_keys + other.missing_line_keys,
            non_string_store_ids=self.non_string_store_ids + other.non_string_store_ids,
            receipts_without_purchase_order=(
                self.receipts_without_purchase_order + other.receipts_without_purchase_order
            ),
        )

    def as_message(self) -> str:
        return (
            f"header_line_mismatches={self.header_line_mismatches} "
            f"missing_line_keys={self.missing_line_keys} "
            f"non_string_store_ids={self.non_string_store_ids} "
            f"receipts_without_purchase_order={self.receipts_without_purchase_order}"
        )


@dataclass(frozen=True, slots=True)
class ParsedHeader:
    business_key: str
    source_path: str
    columns: dict[str, Any]
    lines: tuple[ParsedLine, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedLine:
    business_key: str
    source_path: str
    columns: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PurchasePageParse:
    api_path: str
    response_count: int
    provider_total: int | None
    headers: tuple[ParsedHeader, ...]
    quality: PurchaseQualityReport = field(default_factory=PurchaseQualityReport)

    @property
    def business_keys(self) -> tuple[str, ...]:
        return tuple(header.business_key for header in self.headers)

    @property
    def line_count(self) -> int:
        return sum(len(header.lines) for header in self.headers)


def parse_purchase_page(api_path: str, payload: JsonValue) -> PurchasePageParse:
    if pmc_purchase_provider_code(payload) != "0":
        raise PurchaseParseError("SYNC_PURCHASE_PROVIDER_CODE_INVALID")
    items = pmc_purchase_response_items(api_path, payload)
    if items is None:
        raise PurchaseParseError("SYNC_PURCHASE_RESPONSE_SHAPE_INVALID")
    root = SOURCE_ROOT[api_path]
    total = pmc_purchase_response_total(api_path, payload)
    quality = PurchaseQualityReport()
    headers: list[ParsedHeader] = []
    for ordinal, item in enumerate(items):
        if not isinstance(item, dict):
            raise PurchaseParseError("SYNC_PURCHASE_ITEM_SHAPE_INVALID")
        path = f"{root}[{ordinal}]"
        if api_path == PURCHASE_PLAN_ENDPOINT:
            header, item_quality = _parse_plan(item, path)
        elif api_path == PURCHASE_ORDER_ENDPOINT:
            header, item_quality = _parse_order(item, path)
        elif api_path == RECEIPT_ORDER_ENDPOINT:
            header, item_quality = _parse_receipt(item, path)
        else:
            raise PurchaseParseError("SYNC_PURCHASE_ENDPOINT_UNSUPPORTED")
        headers.append(header)
        quality = quality.merged(item_quality)
    return PurchasePageParse(
        api_path=api_path,
        response_count=len(items),
        provider_total=total,
        headers=tuple(headers),
        quality=quality,
    )


# --- per-endpoint parsers -----------------------------------------------------------


def _parse_plan(item: dict[str, Any], path: str) -> tuple[ParsedHeader, PurchaseQualityReport]:
    plan_sn = _required_key(item, "plan_sn")
    quality = PurchaseQualityReport(non_string_store_ids=_non_string_id(item.get("sid")))
    columns = {
        "plan_sn": plan_sn,
        "status": _int(item.get("status")),
        "status_text": _str(item.get("status_text"), 64),
        "create_time": _time(item.get("create_time")),
        "expect_arrive_time": _time(item.get("expect_arrive_time")),
        "sid": _id(item.get("sid")),
        "seller_name": _str(item.get("seller_name"), 255),
        "sku": _str(item.get("sku"), 255),
        "product_id": _id(item.get("product_id")),
        "product_name": _text(item.get("product_name")),
        "quantity_plan": _int(item.get("quantity_plan")),
        "remark": _text(item.get("remark")),
        "plan_remark": _text(item.get("plan_remark")),
        "purchaser_id": _id(item.get("purchaser_id")),
        "purchaser_name": _str(item.get("purchaser_name"), 255),
        "is_aux": _int(item.get("is_aux")),
        "is_combo": _int(item.get("is_combo")),
        "wid": _id(item.get("wid")),
        "warehouse_name": _str(item.get("warehouse_name"), 255),
        "ppg_sn": _id(item.get("ppg_sn")),
        "payload_json": item,
    }
    return ParsedHeader(plan_sn, path, columns), quality


def _parse_order(item: dict[str, Any], path: str) -> tuple[ParsedHeader, PurchaseQualityReport]:
    order_sn = _required_key(item, "order_sn")
    raw_lines = item.get("item_list")
    lines_source = raw_lines if isinstance(raw_lines, list) else []
    lines: list[ParsedLine] = []
    missing_line_keys = 0
    non_string_store_ids = 0
    planned_total = 0
    for line_ordinal, raw_line in enumerate(lines_source):
        if not isinstance(raw_line, dict):
            raise PurchaseParseError("SYNC_PURCHASE_ITEM_SHAPE_INVALID")
        item_id = _id(raw_line.get("id"))
        if not item_id:
            missing_line_keys += 1
            continue
        non_string_store_ids += _non_string_id(raw_line.get("sid"))
        quantity_plan = _int(raw_line.get("quantity_plan"))
        quantity_real = _int(raw_line.get("quantity_real"))
        # Header quantity_total equals the sum of the lines' *actual* quantities;
        # buyers may adjust a line after planning (rules §5.2 "采购员改过总量").
        # Verified on the 2026-09-22 go-live data: all 138 header/line differences
        # against Σ quantity_plan disappear against Σ quantity_real. Fall back to
        # quantity_plan only when the provider omits quantity_real.
        planned_total += quantity_real if quantity_real is not None else (quantity_plan or 0)
        lines.append(
            ParsedLine(
                business_key=item_id,
                source_path=f"{path}.item_list[{line_ordinal}]",
                columns={
                    "order_sn": order_sn,
                    "item_id": item_id,
                    "line_ordinal": line_ordinal,
                    "plan_sn": _id(raw_line.get("plan_sn")),
                    "sid": _id(raw_line.get("sid")),
                    "sku": _str(raw_line.get("sku"), 255),
                    "product_id": _id(raw_line.get("product_id")),
                    "fnsku": _str(raw_line.get("fnsku"), 64),
                    "quantity_plan": quantity_plan,
                    "quantity_real": quantity_real,
                    "quantity_receive": _int(raw_line.get("quantity_receive")),
                    "quantity_qc": _int(raw_line.get("quantity_qc")),
                    "price": _decimal(raw_line.get("price")),
                    "amount": _decimal(raw_line.get("amount")),
                    "quantity_per_case": _int(raw_line.get("quantity_per_case")),
                    "cases_num": _int(raw_line.get("cases_num")),
                    "expect_arrive_time": _time(raw_line.get("expect_arrive_time")),
                    "wid": _id(raw_line.get("wid")),
                    "is_delete": _int(raw_line.get("is_delete")),
                    "remark": _text(raw_line.get("remark")),
                    "payload_json": raw_line,
                },
            )
        )
    quantity_total = _int(item.get("quantity_total"))
    mismatches = (
        1 if quantity_total is not None and lines and planned_total != quantity_total else 0
    )
    columns = {
        "order_sn": order_sn,
        "custom_order_sn": _str(item.get("custom_order_sn"), 255),
        "status": _int(item.get("status")),
        "status_shipped": _int(item.get("status_shipped")),
        "purchase_type": _int(item.get("purchase_type")),
        "order_time": _time(item.get("order_time")),
        "create_time": _time(item.get("create_time")),
        "auditor_time": _time(item.get("auditor_time")),
        "quantity_total": quantity_total,
        "quantity_receive": _int(item.get("quantity_receive")),
        "quantity_real": _int(item.get("quantity_real")),
        "amount_total": _decimal(item.get("amount_total")),
        "purchase_currency": _str(item.get("purchase_currency"), 16),
        "purchase_rate": _decimal(item.get("purchase_rate")),
        "shipping_price": _decimal(item.get("shipping_price")),
        "other_fee": _decimal(item.get("other_fee")),
        "purchaser_id": _id(item.get("purchaser_id")),
        "item_count": len(lines_source),
        "payload_json": item,
    }
    quality = PurchaseQualityReport(
        header_line_mismatches=mismatches,
        missing_line_keys=missing_line_keys,
        non_string_store_ids=non_string_store_ids,
    )
    return ParsedHeader(order_sn, path, columns, tuple(lines)), quality


def _parse_receipt(item: dict[str, Any], path: str) -> tuple[ParsedHeader, PurchaseQualityReport]:
    order_sn = _required_key(item, "order_sn")
    raw_lines = item.get("item_list")
    lines_source = raw_lines if isinstance(raw_lines, list) else []
    lines: list[ParsedLine] = []
    missing_line_keys = 0
    for line_ordinal, raw_line in enumerate(lines_source):
        if not isinstance(raw_line, dict):
            raise PurchaseParseError("SYNC_PURCHASE_ITEM_SHAPE_INVALID")
        order_item_id = _id(raw_line.get("order_item_id"))
        if not order_item_id:
            missing_line_keys += 1
        lines.append(
            ParsedLine(
                business_key=f"{order_sn}#{line_ordinal}",
                source_path=f"{path}.item_list[{line_ordinal}]",
                columns={
                    "receipt_order_sn": order_sn,
                    "line_ordinal": line_ordinal,
                    "order_item_id": order_item_id,
                    "item_id": _id(raw_line.get("item_id")),
                    "sku": _str(raw_line.get("sku"), 255),
                    "product_name": _text(raw_line.get("product_name")),
                    "fnsku": _str(raw_line.get("fnsku"), 64),
                    "seller_id": _id(raw_line.get("seller_id")),
                    "notice_num_total": _int(raw_line.get("notice_num_total")),
                    "product_receive_num": _int(raw_line.get("product_receive_num")),
                    "quantity_qc_prepare": _int(raw_line.get("quantity_qc_prepare")),
                    "quantity_qc_already": _int(raw_line.get("quantity_qc_already")),
                    "quality_examine_status": _int(raw_line.get("quality_examine_status")),
                    "qc_sn": _id(raw_line.get("qc_sn")),
                    "remark": _text(raw_line.get("remark")),
                    "payload_json": raw_line,
                },
            )
        )
    business_order_sn = _id(item.get("business_order_sn"))
    inbound = item.get("inbound_order_sns")
    columns = {
        "order_sn": order_sn,
        "business_order_sn": business_order_sn,
        "status": _int(item.get("status")),
        "order_type": _int(item.get("order_type")),
        "qc_type": _int(item.get("qc_type")),
        "receive_time": _time(item.get("receive_time")),
        "expect_arrival_time": _time(item.get("expect_arrival_time")),
        "create_time": _time(item.get("create_time")),
        "update_time": _time(item.get("update_time")),
        "wid": _id(item.get("wid")),
        "inbound_order_sns": _string_list(inbound),
        "supplier_id": _id(item.get("supplier_id")),
        "logistics_company": _str(item.get("logistics_company"), 255),
        "logistics_order_no": _str(item.get("logistics_order_no"), 255),
        "shipping_cost": _decimal(item.get("shipping_cost")),
        "shipping_currency": _str(item.get("shipping_currency"), 16),
        "item_count": len(lines_source),
        "payload_json": item,
    }
    quality = PurchaseQualityReport(
        missing_line_keys=missing_line_keys,
        receipts_without_purchase_order=0 if business_order_sn else 1,
    )
    return ParsedHeader(order_sn, path, columns, tuple(lines)), quality


# --- value coercion -----------------------------------------------------------------


def _required_key(item: dict[str, Any], key: str) -> str:
    value = _id(item.get(key))
    if not value:
        raise PurchaseParseError("SYNC_PURCHASE_BUSINESS_KEY_MISSING")
    return value


def _id(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text[:64] or None
    return None


def _non_string_id(value: object) -> int:
    return 1 if isinstance(value, int) and not isinstance(value, bool) else 0


def _str(value: object, limit: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text[:limit] or None
    return None


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _time(value: object) -> str | None:
    return _str(value, 32)


def _int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdecimal():
        return int(value.strip())
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None
    return None


def _string_list(value: object) -> list[str] | None:
    if isinstance(value, list):
        return [str(entry) for entry in value if isinstance(entry, (str, int))]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return None
