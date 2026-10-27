from datetime import date
from decimal import Decimal

from app.modules.warehouse_wfs.fee_detection import resolve_wfs_fees
from app.modules.warehouse_wfs.settlement_parser import parse_settlement_rows


def parse(items):
    return parse_settlement_rows(
        items,
        source_account_ref="account-test",
        expected_store_id="123456789012345678",
        window_start=date(2026, 9, 1),
        window_end=date(2026, 10, 20),
    )


def row(index, qty, fee):
    return {
        "storeName": "Shop A",
        "storeId": "123456789012345678",
        "msku": "SKU-TEST",
        "settlementDate": "2026-10-10",
        "uniqueId": "order-1",
        "rowIndex": str(index),
        "platformOrderNo": "platform-order-1",
        "salesNum": qty,
        "platformLogisticsAmount": fee,
        "currencyCode": "USD",
        "platformCode": "10008",
        "transactionTypes": 0,
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
    item["storeId"] = "999999999999999999"
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


def test_cs_sku_is_business_excluded_not_invalid() -> None:
    item = row(0, 10, "-40")
    item["msku"] = "CS-BUSINESS-EXCLUDED"

    result = parse([item])

    assert result.rows == ()
    assert result.business_excluded_rows == 1
    assert result.rejected_rows == 0


def test_outside_window_rejected():
    item = row(0, 10, "-40")
    item["settlementDate"] = "2026-08-01"
    assert len(parse([item]).rows) == 0


def test_invalid_money_rejected():
    item = row(0, 10, "invalid")
    result = parse([item])
    assert len(result.rows) == 0
    assert result.rejected_rows == 1


def test_non_usd_and_missing_order_are_rejected():
    non_usd = row(0, 10, "-40")
    non_usd["currencyCode"] = "EUR"
    missing_order = row(1, 10, "-40")
    missing_order["platformOrderNo"] = ""

    result = parse([non_usd, missing_order])

    assert result.rows == ()
    assert result.rejected_rows == 2
    assert result.missing_identity == 1


def test_reject_invalid_units_without_losing_valid_duplicate_identity() -> None:
    for quantity in ("-1", "1.5", "-0.5"):
        invalid = row(0, quantity, "-6.95")
        valid = row(0, 10, "-46.50")
        result = parse([invalid, valid])
        assert result.invalid_rows == 1
        assert result.duplicate_rows == 0
        assert result.accepted_rows == 1
        assert result.rows[0].sales_num == Decimal("10")


def test_keep_zero_quantity_fee_line_for_order_pairing() -> None:
    result = parse([row(0, 10, 0), row(1, 0, "-46.50")])
    assert result.invalid_rows == 0
    assert resolve_wfs_fees(list(result.rows))[0].unit_fee == Decimal("4.65")


def test_mixed_page_classifies_every_provider_row_without_hiding_errors() -> None:
    accepted = row(0, 10, "-40")
    excluded = row(1, 1, "-4")
    excluded["msku"] = "CS-EXCLUDED"
    invalid_currency = row(2, 1, "-4")
    invalid_currency["currencyCode"] = "EUR"
    missing_identity = row(3, 1, "-4")
    missing_identity["platformOrderNo"] = ""
    missing_store = row(4, 1, "-4")
    missing_store["storeId"] = ""
    duplicate = accepted.copy()

    result = parse(
        [accepted, excluded, invalid_currency, missing_identity, missing_store, duplicate]
    )

    assert result.accepted_rows == 1
    assert result.business_excluded_rows == 1
    assert result.invalid_rows == 1
    assert result.missing_identity_rows == 1
    assert result.missing_store_rows == 1
    assert result.duplicate_rows == 1
    assert (
        sum(
            (
                result.accepted_rows,
                result.business_excluded_rows,
                result.invalid_rows,
                result.missing_identity_rows,
                result.missing_store_rows,
                result.duplicate_rows,
            )
        )
        == 6
    )
