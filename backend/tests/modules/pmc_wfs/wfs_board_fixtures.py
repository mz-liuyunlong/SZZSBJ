"""Synthetic Lingxing WFS pages shaped like the official field tables (no real identifiers)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

STORE_A = "110000000000000001"
STORE_B = "110000000000000002"


def cargo(
    cargo_id: str,
    cargo_code: str,
    *,
    store_id: str = STORE_A,
    store_name: str = "CN0001-Test Store",
    status: int = 1,
    status_name: str = "AWAITING_DELIVERY",
    shipping_codes: list[str] | None = None,
    goods: list[dict[str, Any]] | None = None,
    in_bound_order_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": cargo_id,
        "in_bound_order_id": in_bound_order_id or f"PMC-{cargo_code}",
        "store_id": store_id,
        "store_name": store_name,
        "country_name": "美国",
        "creator": "",
        "shipping_list_codes": shipping_codes if shipping_codes is not None else [],
        "logistics_code": "LAX2T",
        "cargo_create_date": "2026-10-16 15:23:28",
        "cargo_code": cargo_code,
        "update_date": "2026-10-16 15:42:18",
        "system_update_date": "2026-10-16 15:42:59",
        "cargo_status": status_name,
        "status_name": status_name,
        "status": status,
        "cargo_sync_status": "已申报",
        "distribution_addresses": "1 Test Ave,Chino,CA,美国,US,91708",
        "return_addresses": "2 Test Ave,CHINO,CA,美国,US",
        "to_pending_time": 1792136538901,
        "to_await_time": 1792140000000 if status >= 1 else 0,
        "to_receive_time": 1792300000000 if status >= 2 else 0,
        "to_closed_time": 1792500000000 if status == 3 else 0,
        "to_cancelled_time": 1792500000000 if status == 4 else 0,
        "cargo_good_list": goods
        if goods is not None
        else [
            {
                "msku": "TSKU-1U",
                "sku": "TSKU",
                "product_name": "测试商品",
                "gtin": "00000000000011",
                "shipments_num": "72",
                "received_num": "0",
                "dameged_qty": "0",
                "declare_num": "72",
            }
        ],
    }


def shipping_list(
    shipping_code: str,
    *,
    cargo_codes: list[str],
    status: str = "已发货",
    actual_delivery_time: str = "2026-10-18 10:00:00",
    arrival_time: str = "",
) -> dict[str, Any]:
    return {
        "shipping_code": shipping_code,
        "shipping_status": status,
        "delivery_time": "1970-01-01",
        "warehouse_id": 16168,
        "logistics_provider_id": 6995,
        "logistics_channel_id": 12876,
        "creator": "运营A",
        "gmt_create": "2026-10-16 15:47:44",
        "actual_delivery_time": actual_delivery_time,
        "arrival_time": arrival_time,
        "sail_time": "",
        "expected_arrival_time": "2026-11-05",
        "actual_due_ime": "",
        "logistics_code": "LAX2T",
        "principal_user_name": "",
        "shipping_remark": "",
        "head_fee_type": "按计费重",
        "order_logistics_status": "",
        "shipping_list_files": None,
        "shipping_logistics": [
            {"logistics_number": f"ZY{shipping_code[-6:]}", "tracking_number": ""}
        ],
        "shipping_goods": [
            {
                "store_id": STORE_A,
                "cargo_code": code,
                "msku": "TSKU-1U",
                "sku": "TSKU",
                "quantity_in_case": "14",
                "box_num": "2",
                "apply_num": "28",
                "shipments_num": "28",
            }
            for code in cargo_codes
        ],
        "shipping_accessories": None,
        "shipping_first_lets": None,
    }


def page(records: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {
        "code": 0,
        "message": "success",
        "error_details": [],
        "request_id": "test",
        "response_time": "2026-10-30 10:00:00",
        "data": {"total": str(total), "records": deepcopy(records)},
    }


CARGOS = [
    cargo("23212872", "3292441WFB", shipping_codes=["SP202610160010009"]),
    cargo(
        "23212873",
        "3292442WFB",
        store_id=STORE_B,
        store_name="HK0002-Test Store",
        status=2,
        status_name="RECEIVING_IN_PROGRESS",
        goods=[
            {
                "msku": "TSKU2-1U",
                "sku": "TSKU2",
                "product_name": "测试商品2",
                "gtin": "00000000000022",
                "shipments_num": "40",
                "received_num": "38",
                "dameged_qty": "2",
                "declare_num": "40",
            },
            {
                "msku": "TSKU3-1U",
                "sku": "TSKU3",
                "product_name": "测试商品3",
                "gtin": "00000000000033",
                "shipments_num": "10",
                "received_num": "10",
                "dameged_qty": "0",
                "declare_num": "10",
            },
        ],
    ),
    cargo("23212874", "3292443WFB", status=0, status_name="PENDING_SHIPMENT_DETAILS", goods=[]),
]

SHIPPING_LISTS = [
    shipping_list("SP202610160010009", cargo_codes=["3292441WFB"]),
    # Linked only through shipping_goods[].cargo_code (cargo has no shipping_list_codes).
    shipping_list(
        "SP202610170010010",
        cargo_codes=["3292442WFB"],
        actual_delivery_time="2026-10-19 09:30:00",
        arrival_time="2026-10-28 00:00:00",
    ),
]
