from decimal import Decimal

import pytest

from app.integrations.lingxing.pmc_purchase_contracts import (
    PURCHASE_ORDER_ENDPOINT,
    PURCHASE_PLAN_ENDPOINT,
    RECEIPT_ORDER_ENDPOINT,
)
from app.modules.integration_sync.parsers.lingxing_purchase import (
    PARSER_KEYS,
    PurchaseParseError,
    parse_purchase_page,
)

PLAN_PAYLOAD = {
    "code": 0,
    "total": 2,
    "data": [
        {
            "plan_sn": "PP26090001",
            "status": 2,
            "status_text": "待采购",
            "create_time": "2026-09-01 10:00:00",
            "sid": 110687423514268160,
            "seller_name": "CN2601",
            "sku": "YC00001",
            "product_id": 1045003,
            "product_name": "测试品",
            "quantity_plan": 300,
            "remark": "ITEMID:20039257883",
            "is_aux": 0,
            "is_combo": 0,
            "wid": 16168,
        },
        {"plan_sn": "PP26090002", "status": 3, "quantity_plan": "50", "sid": "0"},
    ],
}

ORDER_PAYLOAD = {
    "code": 0,
    "data": [
        {
            "order_sn": "PO260901001",
            "status": 3,
            "status_shipped": 1,
            "order_time": "2026-09-01 09:00:00",
            "auditor_time": "2026-09-01 12:00:00",
            "quantity_total": 500,
            "quantity_receive": 200,
            "amount_total": "1234.5",
            "purchase_currency": "CNY",
            "purchase_rate": 1,
            "item_list": [
                {"id": 9001, "sku": "YC00001", "sid": "0", "quantity_plan": 300, "price": "2.5"},
                {"id": 9002, "sku": "YC00002", "sid": 110687423514268160, "quantity_plan": 200},
            ],
        },
        {
            "order_sn": "PO260901002",
            "quantity_total": 10,
            "item_list": [{"id": 9003, "quantity_plan": 7}, {"sku": "NOID", "quantity_plan": 3}],
        },
    ],
}

RECEIPT_PAYLOAD = {
    "code": 0,
    "data": {
        "total": 1,
        "list": [
            {
                "order_sn": "RC260905001",
                "business_order_sn": "PO260901001",
                "status": 3,
                "receive_time": "2026-09-05 15:00:00",
                "inbound_order_sns": ["IB260905001", "IB260905002"],
                "wid": 16168,
                "shipping_cost": "88.00",
                "item_list": [
                    {
                        "order_item_id": 9001,
                        "sku": "YC00001",
                        "seller_id": "110687423514268160",
                        "notice_num_total": 300,
                        "product_receive_num": 200,
                    },
                    {"sku": "YC00002", "notice_num_total": 200, "product_receive_num": 0},
                ],
            },
            {"order_sn": "RC260905002", "item_list": []},
        ],
    },
}


def test_plan_page_parses_headers_and_coerces_types() -> None:
    parsed = parse_purchase_page(PURCHASE_PLAN_ENDPOINT, PLAN_PAYLOAD)
    assert parsed.response_count == 2 and parsed.provider_total == 2
    assert parsed.business_keys == ("PP26090001", "PP26090002")
    first = parsed.headers[0]
    assert first.source_path == "$.data[0]"
    assert first.columns["sid"] == "110687423514268160"
    assert first.columns["product_id"] == "1045003"
    assert first.columns["quantity_plan"] == 300
    assert first.columns["remark"] == "ITEMID:20039257883"
    assert first.columns["payload_json"] is PLAN_PAYLOAD["data"][0]
    assert parsed.headers[1].columns["quantity_plan"] == 50
    assert parsed.quality.non_string_store_ids == 1
    assert parsed.line_count == 0


def test_order_page_splits_headers_and_lines_and_reports_quality() -> None:
    parsed = parse_purchase_page(PURCHASE_ORDER_ENDPOINT, ORDER_PAYLOAD)
    assert parsed.provider_total is None
    assert parsed.business_keys == ("PO260901001", "PO260901002")
    head, second = parsed.headers
    assert head.columns["amount_total"] == Decimal("1234.5")
    assert head.columns["purchase_rate"] == Decimal("1")
    assert head.columns["item_count"] == 2
    assert [line.business_key for line in head.lines] == ["9001", "9002"]
    assert head.lines[0].source_path == "$.data[0].item_list[0]"
    assert head.lines[0].columns["price"] == Decimal("2.5")
    assert head.lines[0].columns["line_ordinal"] == 0
    assert head.lines[1].columns["sid"] == "110687423514268160"
    # second order: one line lacks id -> skipped and counted; 7 != 10 -> mismatch counted
    assert [line.business_key for line in second.lines] == ["9003"]
    assert second.columns["item_count"] == 2
    assert parsed.quality.missing_line_keys == 1
    assert parsed.quality.header_line_mismatches == 1
    assert parsed.quality.non_string_store_ids == 1
    assert parsed.line_count == 3


def test_receipt_page_reads_nested_list_and_keeps_line_ordinals() -> None:
    parsed = parse_purchase_page(RECEIPT_ORDER_ENDPOINT, RECEIPT_PAYLOAD)
    assert parsed.provider_total == 1
    assert parsed.response_count == 2
    head = parsed.headers[0]
    assert head.source_path == "$.data.list[0]"
    assert head.columns["business_order_sn"] == "PO260901001"
    assert head.columns["inbound_order_sns"] == ["IB260905001", "IB260905002"]
    assert head.columns["shipping_cost"] == Decimal("88.00")
    assert head.columns["item_count"] == 2
    assert [line.business_key for line in head.lines] == ["RC260905001#0", "RC260905001#1"]
    assert head.lines[0].columns["order_item_id"] == "9001"
    assert head.lines[1].columns["order_item_id"] is None
    assert parsed.quality.missing_line_keys == 1
    assert parsed.quality.receipts_without_purchase_order == 1


@pytest.mark.parametrize(
    ("api_path", "payload", "code"),
    [
        (PURCHASE_PLAN_ENDPOINT, {"code": 1, "data": []}, "SYNC_PURCHASE_PROVIDER_CODE_INVALID"),
        (
            PURCHASE_PLAN_ENDPOINT,
            {"code": 0, "data": {"x": 1}},
            "SYNC_PURCHASE_RESPONSE_SHAPE_INVALID",
        ),
        (RECEIPT_ORDER_ENDPOINT, {"code": 0, "data": []}, "SYNC_PURCHASE_RESPONSE_SHAPE_INVALID"),
        (PURCHASE_PLAN_ENDPOINT, {"code": 0, "data": ["x"]}, "SYNC_PURCHASE_ITEM_SHAPE_INVALID"),
        (
            PURCHASE_PLAN_ENDPOINT,
            {"code": 0, "data": [{"sku": "A"}]},
            "SYNC_PURCHASE_BUSINESS_KEY_MISSING",
        ),
        (
            PURCHASE_ORDER_ENDPOINT,
            {"code": 0, "data": [{"order_sn": "PO1", "item_list": ["bad"]}]},
            "SYNC_PURCHASE_ITEM_SHAPE_INVALID",
        ),
    ],
)
def test_structural_failures_raise_stable_codes(api_path: str, payload: dict, code: str) -> None:
    with pytest.raises(PurchaseParseError) as error:
        parse_purchase_page(api_path, payload)
    assert error.value.code == code


def test_parser_keys_are_versioned_per_endpoint() -> None:
    assert set(PARSER_KEYS) == {
        PURCHASE_PLAN_ENDPOINT,
        PURCHASE_ORDER_ENDPOINT,
        RECEIPT_ORDER_ENDPOINT,
    }
    assert all(
        key.startswith("lingxing.pmc_purchase.") and key.endswith(".v1")
        for key in PARSER_KEYS.values()
    )
