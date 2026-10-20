from datetime import date
from decimal import Decimal

from app.modules.warehouse_wfs.fee_detection import resolve_wfs_fees
from app.modules.warehouse_wfs.settlement_parser import parse_settlement_rows


def parse(items):
    return parse_settlement_rows(
        items,
        source_account_ref="account-test",
        store_ids_by_name={"Shop A": "123456789012345678"},
        window_start=date(2026, 9, 1),
        window_end=date(2026, 10, 20),
    )


def row(index, qty, fee):
    return {
        "storeName": "Shop A",
        "msku": "SKU-TEST",
        "settlementDate": "2026-10-10",
        "uniqueId": "order-1",
        "rowIndex": str(index),
        "platformOrderNo": "platform-order-1",
        "salesNum": qty,
        "platformLogisticsAmount": fee,
    }


def test_parse_and_resolve_fee():
    result = parse(
        [
            row(0, 10, 0),
            row(1, 0, "-46.50"),
        ]
    )
    assert result.rejected_rows == 0
    assert len(result.rows) == 2
    assert result.rows[0].store_id == "123456789012345678"

    fees = resolve_wfs_fees(list(result.rows))
    assert fees[0].unit_fee == Decimal("4.65")


def test_unknown_store_is_not_assigned():
    item = row(0, 10, "-40")
    item["storeName"] = "Unknown Shop"
    result = parse([item])
    assert len(result.rows) == 0
    assert result.missing_store == 1


def test_duplicate_line_not_double_counted():
    item = row(0, 10, "-40")
    result = parse([item, item.copy()])
    assert len(result.rows) == 1
    assert result.duplicate_lines == 1


def test_missing_line_identity_rejected():
    item = row(0, 10, "-40")
    item.pop("rowIndex")
    result = parse([item])
    assert len(result.rows) == 0
    assert result.missing_identity == 1


def test_outside_window_rejected():
    item = row(0, 10, "-40")
    item["settlementDate"] = "2026-08-01"
    assert len(parse([item]).rows) == 0


def test_invalid_money_rejected():
    item = row(0, 10, "invalid")
    result = parse([item])
    assert len(result.rows) == 0
    assert result.rejected_rows == 1
