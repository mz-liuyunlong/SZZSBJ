"""Parse WFS shipment-board Lingxing pages into ODS column dicts.

The cargo page yields one header row per record plus one child row per
``cargo_good_list[]`` line; the shipping-list page yields one header row per record with
the nested goods / logistics arrays reduced to the identifiers and totals the board needs.
The full record is always kept in ``payload_json`` so later rebuilds never need Lingxing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from pydantic import JsonValue

from app.integrations.lingxing.pmc_wfs_contracts import (
    WFS_CARGO_PAGE_ENDPOINT,
    WFS_SHIPPING_LIST_PAGE_ENDPOINT,
    pmc_wfs_response_items,
    pmc_wfs_response_total,
)

PARSER_VERSION: Final = "lingxing.wfs_board.v1"
PARSER_KEYS: Final[dict[str, str]] = {
    WFS_CARGO_PAGE_ENDPOINT: "lingxing.pmc_wfs.cargo_page.v1",
    WFS_SHIPPING_LIST_PAGE_ENDPOINT: "lingxing.pmc_wfs.shipping_list_page.v1",
}


class WfsBoardParseError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ParsedWfsRow:
    business_key: str
    source_path: str
    columns: dict[str, Any]
    children: tuple[ParsedWfsRow, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class WfsPageParse:
    headers: tuple[ParsedWfsRow, ...]
    response_count: int
    provider_total: int | None


def parse_wfs_page(api_path: str, payload: JsonValue) -> WfsPageParse:
    items = pmc_wfs_response_items(api_path, payload)
    if items is None:
        raise WfsBoardParseError("SYNC_WFS_ITEM_SHAPE_INVALID")
    parsed: list[ParsedWfsRow] = []
    for ordinal, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise WfsBoardParseError("SYNC_WFS_ITEM_SHAPE_INVALID")
        path = f"$.data.records[{ordinal}]"
        if api_path == WFS_CARGO_PAGE_ENDPOINT:
            parsed.append(_parse_cargo(raw, path))
        elif api_path == WFS_SHIPPING_LIST_PAGE_ENDPOINT:
            parsed.append(_parse_shipping_list(raw, path))
        else:
            raise WfsBoardParseError("SYNC_WFS_ENDPOINT_UNSUPPORTED")
    return WfsPageParse(
        headers=tuple(parsed),
        response_count=len(items),
        provider_total=pmc_wfs_response_total(payload),
    )


def _parse_cargo(item: dict[str, Any], path: str) -> ParsedWfsRow:
    cargo_id = _id(item.get("id"))
    if cargo_id is None:
        raise WfsBoardParseError("SYNC_WFS_CARGO_ID_MISSING")
    goods_raw = item.get("cargo_good_list")
    goods: list[ParsedWfsRow] = []
    if goods_raw is not None:
        if not isinstance(goods_raw, list):
            raise WfsBoardParseError("SYNC_WFS_CARGO_GOODS_SHAPE_INVALID")
        for line_ordinal, good in enumerate(goods_raw):
            if not isinstance(good, dict):
                raise WfsBoardParseError("SYNC_WFS_CARGO_GOODS_SHAPE_INVALID")
            goods.append(
                ParsedWfsRow(
                    business_key=f"{cargo_id}#{line_ordinal}",
                    source_path=f"{path}.cargo_good_list[{line_ordinal}]",
                    columns={
                        "cargo_id": cargo_id,
                        "cargo_code": _str(item.get("cargo_code"), 64),
                        "line_ordinal": line_ordinal,
                        "msku": _str(good.get("msku"), 255),
                        "sku": _str(good.get("sku"), 255),
                        "product_name": _str(good.get("product_name"), 500),
                        "gtin": _str(good.get("gtin"), 64),
                        "declare_num": _int(good.get("declare_num")),
                        "shipments_num": _int(good.get("shipments_num")),
                        "received_num": _int(good.get("received_num")),
                        # Provider field is spelled "dameged_qty" in the official table.
                        "damaged_qty": _int(good.get("dameged_qty", good.get("damaged_qty"))),
                        "payload_json": good,
                    },
                )
            )
    columns: dict[str, Any] = {
        "cargo_id": cargo_id,
        "cargo_code": _str(item.get("cargo_code"), 64),
        "in_bound_order_id": _str(item.get("in_bound_order_id"), 128),
        "store_id": _id(item.get("store_id")),
        "store_name": _str(item.get("store_name"), 255),
        "country_name": _str(item.get("country_name"), 64),
        "creator": _str(item.get("creator"), 128),
        "logistics_code": _str(item.get("logistics_code"), 64),
        "cargo_create_date": _time(item.get("cargo_create_date")),
        "update_date": _time(item.get("update_date")),
        "system_update_date": _time(item.get("system_update_date")),
        "status": _int(item.get("status")),
        "cargo_status": _str(item.get("cargo_status"), 64),
        "status_name": _str(item.get("status_name"), 64),
        "cargo_sync_status": _str(item.get("cargo_sync_status"), 64),
        "shipping_list_codes": _str_list(item.get("shipping_list_codes")),
        "distribution_addresses": _text(item.get("distribution_addresses")),
        "return_addresses": _text(item.get("return_addresses")),
        "to_pending_at": _epoch_ms(item.get("to_pending_time")),
        "to_await_at": _epoch_ms(item.get("to_await_time")),
        "to_receive_at": _epoch_ms(item.get("to_receive_time")),
        "to_closed_at": _epoch_ms(item.get("to_closed_time")),
        "to_cancelled_at": _epoch_ms(item.get("to_cancelled_time")),
        "goods_count": len(goods),
        "payload_json": item,
    }
    return ParsedWfsRow(
        business_key=cargo_id, source_path=path, columns=columns, children=tuple(goods)
    )


def _parse_shipping_list(item: dict[str, Any], path: str) -> ParsedWfsRow:
    shipping_code = _str(item.get("shipping_code"), 64)
    if not shipping_code:
        raise WfsBoardParseError("SYNC_WFS_SHIPPING_CODE_MISSING")
    goods = item.get("shipping_goods")
    goods_list = goods if isinstance(goods, list) else []
    logistics = item.get("shipping_logistics")
    logistics_list = logistics if isinstance(logistics, list) else []
    cargo_codes = sorted(
        {
            code
            for good in goods_list
            if isinstance(good, dict)
            for code in [_str(good.get("cargo_code"), 64)]
            if code
        }
    )
    logistics_numbers = [
        number
        for entry in logistics_list
        if isinstance(entry, dict)
        for number in [_str(entry.get("logistics_number"), 128)]
        if number
    ]
    tracking_numbers = [
        number
        for entry in logistics_list
        if isinstance(entry, dict)
        for number in [_str(entry.get("tracking_number"), 128)]
        if number
    ]
    columns: dict[str, Any] = {
        "shipping_code": shipping_code,
        "shipping_status": _str(item.get("shipping_status"), 32),
        "warehouse_id": _id(item.get("warehouse_id")),
        "logistics_provider_id": _id(item.get("logistics_provider_id")),
        "logistics_channel_id": _id(item.get("logistics_channel_id")),
        "logistics_code": _str(item.get("logistics_code"), 64),
        "creator": _str(item.get("creator"), 128),
        "principal_user_name": _str(item.get("principal_user_name"), 128),
        "gmt_create": _time(item.get("gmt_create")),
        "delivery_time": _time(item.get("delivery_time")),
        "actual_delivery_time": _time(item.get("actual_delivery_time")),
        "sail_time": _time(item.get("sail_time")),
        "arrival_time": _time(item.get("arrival_time")),
        "expected_arrival_time": _time(item.get("expected_arrival_time")),
        # Provider field is spelled "actual_due_ime" in the official table.
        "actual_due_time": _time(item.get("actual_due_ime", item.get("actual_due_time"))),
        "order_logistics_status": _str(item.get("order_logistics_status"), 64),
        "head_fee_type": _str(item.get("head_fee_type"), 64),
        "shipping_remark": _text(item.get("shipping_remark")),
        "cargo_codes": cargo_codes,
        "logistics_numbers": logistics_numbers,
        "tracking_numbers": tracking_numbers,
        "goods_count": len(goods_list),
        "box_num_total": _sum_int(goods_list, "box_num"),
        "shipments_num_total": _sum_int(goods_list, "shipments_num"),
        "payload_json": item,
    }
    return ParsedWfsRow(business_key=shipping_code, source_path=path, columns=columns)


def _id(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()[:64]
    return None


def _str(value: object, limit: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                number = float(text)
            except ValueError:
                return None
            return int(number) if number.is_integer() else None
    return None


def _time(value: object) -> str | None:
    """Provider time strings are kept verbatim (Asia/Shanghai wall clock); empty → None."""

    text = _str(value, 32)
    if text in (None, "1970-01-01", "1970-01-01 00:00:00", "0"):
        return None
    return text


def _epoch_ms(value: object) -> datetime | None:
    number = _int(value)
    if number is None or number <= 0:
        return None
    return datetime.fromtimestamp(number / 1000, tz=UTC)


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [code for code in (_str(v, 64) for v in value) if code]


def _sum_int(rows: list[Any], key: str) -> int | None:
    total = 0
    seen = False
    for row in rows:
        if isinstance(row, dict):
            number = _int(row.get(key))
            if number is not None:
                total += number
                seen = True
    return total if seen else None
