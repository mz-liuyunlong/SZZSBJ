"""Parse domestic warehouse Lingxing pages into ODS column dicts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from pydantic import JsonValue

from app.integrations.lingxing.pmc_domestic_contracts import (
    BATCH_DETAIL_LIST_ENDPOINT,
    BATCH_STATEMENT_LIST_ENDPOINT,
    INVENTORY_DETAILS_ENDPOINT,
    WAREHOUSE_LIST_ENDPOINT,
    WAREHOUSE_STATEMENT_ENDPOINT,
    pmc_domestic_response_items,
    pmc_domestic_response_total,
)

PARSER_VERSION: Final = "lingxing.domestic.v1"
PARSER_KEYS: Final[dict[str, str]] = {
    WAREHOUSE_STATEMENT_ENDPOINT: "lingxing.pmc_domestic.warehouse_statement.v1",
    WAREHOUSE_LIST_ENDPOINT: "lingxing.pmc_domestic.warehouse_list.v1",
    INVENTORY_DETAILS_ENDPOINT: "lingxing.pmc_domestic.inventory_details.v1",
    BATCH_DETAIL_LIST_ENDPOINT: "lingxing.pmc_domestic.batch_detail_list.v1",
    BATCH_STATEMENT_LIST_ENDPOINT: "lingxing.pmc_domestic.batch_statement_list.v1",
}


class DomesticParseError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ParsedDomesticRow:
    business_key: str
    source_path: str
    columns: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DomesticPageParse:
    headers: tuple[ParsedDomesticRow, ...]
    response_count: int
    provider_total: int | None


def parse_domestic_page(api_path: str, payload: JsonValue) -> DomesticPageParse:
    items = pmc_domestic_response_items(api_path, payload)
    if items is None:
        raise DomesticParseError("SYNC_DOMESTIC_ITEM_SHAPE_INVALID")
    parsed: list[ParsedDomesticRow] = []
    for ordinal, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise DomesticParseError("SYNC_DOMESTIC_ITEM_SHAPE_INVALID")
        path = f"$.data[{ordinal}]"
        if api_path == WAREHOUSE_LIST_ENDPOINT:
            parsed.append(_parse_warehouse(raw, path))
        elif api_path == INVENTORY_DETAILS_ENDPOINT:
            parsed.append(_parse_inventory(raw, path))
        elif api_path == BATCH_DETAIL_LIST_ENDPOINT:
            parsed.append(_parse_batch(raw, path))
        elif api_path == WAREHOUSE_STATEMENT_ENDPOINT:
            from app.modules.pmc_domestic.inbound_builder import (
                InboundDataError,
                quantity,
                source_id,
            )

            try:
                columns = {
                    k: source_id(raw.get(k))
                    for k in (
                        "order_sn",
                        "ref_order_sn",
                        "sku",
                        "product_id",
                        "sub_type",
                        "opt_time",
                    )
                }
                columns.update(
                    {
                        k: quantity(raw.get(k))
                        for k in (
                            "product_total",
                            "product_qc_num",
                            "product_good_num",
                            "product_bad_num",
                        )
                    }
                )
                columns.update(
                    statement_id=source_id(raw.get("statement_id"), required=True),
                    source_warehouse_id=source_id(raw.get("wid"), required=True),
                    payload_json=raw,
                )
                parsed.append(
                    ParsedDomesticRow(
                        business_key=columns["statement_id"], source_path=path, columns=columns
                    )
                )
            except InboundDataError:
                raise DomesticParseError("SYNC_DOMESTIC_STATEMENT_INVALID") from None
        elif api_path == BATCH_STATEMENT_LIST_ENDPOINT:
            parsed.append(_parse_event(raw, path, ordinal))
        else:
            raise DomesticParseError("SYNC_DOMESTIC_ENDPOINT_UNKNOWN")
    return DomesticPageParse(
        headers=tuple(parsed),
        response_count=len(parsed),
        provider_total=pmc_domestic_response_total(payload),
    )


def _parse_warehouse(item: dict[str, Any], path: str) -> ParsedDomesticRow:
    wid = _id(item.get("wid"))
    if not wid:
        raise DomesticParseError("SYNC_DOMESTIC_BUSINESS_KEY_MISSING")
    return ParsedDomesticRow(
        business_key=wid,
        source_path=path,
        columns={
            "source_warehouse_id": wid,
            "warehouse_name": _str(item.get("name"), 255),
            "warehouse_type": _str(item.get("type"), 64),
            "sub_type": _str(item.get("sub_type"), 64),
            "payload_json": item,
        },
    )


def _parse_inventory(item: dict[str, Any], path: str) -> ParsedDomesticRow:
    wid = _id(item.get("wid")) or "0"
    sku = _str(item.get("sku"), 255) or ""
    seller = _id(item.get("seller_id")) or ""
    return ParsedDomesticRow(
        business_key=f"{wid}|{sku}|{seller}",
        source_path=path,
        columns={
            "source_warehouse_id": wid if wid != "0" else _id(item.get("wid")) or "0",
            "product_id": _id(item.get("product_id")),
            "sku": _str(item.get("sku"), 255),
            "seller_id": _id(item.get("seller_id")),
            "fnsku": _id(item.get("fnsku")),
            "product_total": _int(item.get("product_total")),
            "product_valid_num": _int(item.get("product_valid_num")),
            "product_bad_num": _int(item.get("product_bad_num")),
            "product_qc_num": _int(item.get("product_qc_num")),
            "product_lock_num": _int(item.get("product_lock_num")),
            "good_lock_num": _int(item.get("good_lock_num")),
            "quantity_receive": _int(item.get("quantity_receive")),
            "payload_json": item,
        },
    )


def _parse_batch(item: dict[str, Any], path: str) -> ParsedDomesticRow:
    wid = _id(item.get("wid")) or "0"
    batch_no = _id(item.get("batch_no")) or ""
    sku = _str(item.get("sku"), 255) or ""
    store_id = _id(item.get("store_id")) or ""
    key = f"{wid}|{batch_no}|{sku}|{store_id}"
    purchase_orders = item.get("purchase_order_sns")
    return ParsedDomesticRow(
        business_key=key,
        source_path=path,
        columns={
            "source_warehouse_id": wid,
            "warehouse_name": _str(item.get("wh_name"), 255),
            "batch_no": _id(item.get("batch_no")),
            "source_batch_no": _join_scalar(item.get("source_batch_no")),
            "order_sn": _id(item.get("order_sn")),
            "batch_type": _int(item.get("type")),
            "batch_type_name": _str(item.get("type_name"), 64),
            "sku": _str(item.get("sku"), 255),
            "product_id": _id(item.get("product_id")),
            "product_name": _text(item.get("product_name")),
            "store_id": _id(item.get("store_id")),
            "store_name": _str(item.get("store_name"), 255),
            "msku": _str(item.get("msku"), 255),
            "fnsku": _id(item.get("fnsku")),
            "total_qty": _int(item.get("total")),
            "balance_num": _int(item.get("balance_num")),
            "good_num": _int(item.get("good_num")),
            "bad_num": _int(item.get("bad_num")),
            "qc_num": _int(item.get("qc_num")),
            "purchase_order_sns": _join_list(purchase_orders),
            "purchase_in_time": _time(item.get("purchase_in_time")),
            "batch_time": _time(item.get("batch_time")),
            "payload_json": item,
        },
    )


def _parse_event(item: dict[str, Any], path: str, ordinal: int) -> ParsedDomesticRow:
    statement_id = _id(item.get("statement_id"))
    wid = _id(item.get("wid")) or _id(item.get("source_wid")) or "0"
    order_sn = _id(item.get("order_sn")) or ""
    opt_time = _time(item.get("opt_time")) or ""
    business_key = statement_id or f"{wid}|{order_sn}|{opt_time}|{ordinal}"
    return ParsedDomesticRow(
        business_key=business_key,
        source_path=path,
        columns={
            "statement_id": statement_id,
            "source_warehouse_id": wid,
            "warehouse_name": _str(item.get("wh_name") or item.get("warehouse_name"), 255),
            "order_sn": _id(item.get("order_sn")),
            "ref_order_sn": _id(item.get("ref_order_sn")),
            "sku": _str(item.get("sku"), 255),
            "product_id": _id(item.get("product_id")),
            "seller_id": _id(item.get("seller_id")),
            "fnsku": _id(item.get("fnsku")),
            "event_type": _int(item.get("type") or item.get("event_type")),
            "sub_type": _int(item.get("sub_type")),
            "product_good_num": _int(item.get("product_good_num") or item.get("good_num")),
            "product_bad_num": _int(item.get("product_bad_num") or item.get("bad_num")),
            "product_qc_num": _int(item.get("product_qc_num") or item.get("qc_num")),
            "opt_time": _time(item.get("opt_time") or item.get("operate_time")),
            "remark": _text(item.get("remark")),
            "payload_json": item,
        },
    )


def _id(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text or None
    return None


def _str(value: object, limit: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, Decimal):
        return int(value)
    return None


def _time(value: object) -> str | None:
    return _str(value, 32)


def _join_list(value: object) -> str | None:
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ",".join(parts) if parts else None
    return _text(value)


def _join_scalar(value: object) -> str | None:
    if isinstance(value, list):
        return _join_list(value)
    return _id(value) or _text(value)
