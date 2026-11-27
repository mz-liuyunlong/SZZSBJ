"""沃尔玛账单解析与时间段切分：纯函数，合成数据，不需要数据库。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.modules.integration_sync.handlers.lingxing_walmart_bill_sync import (
    month_segments,
    rolling_window,
)
from app.modules.integration_sync.walmart_bill_catalog import WALMART_BILL_SYNC_SPEC
from app.modules.walmart_bills.parsing import (
    BillRowError,
    bill_page,
    identity_base,
    line_key,
    parse_bill_row,
    row_hash,
)
from app.modules.walmart_bills.periods import period_status

STORE = "900000000000000001"
WINDOW = (date(2026, 10, 1), date(2026, 10, 31))


def line(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 900000000000000123,
        "storeId": STORE,
        "storeName": "合成店铺",
        "companyId": 1,
        "reportKey": "rk-synthetic-1",
        "reportId": 77,
        "reportDate": "2026-10-20",
        "periodStartDate": None,
        "periodEndDate": None,
        "transactionPostedTimestamp": "2026-10-05 00:00:00",
        "transactionKey": "tk-1",
        "transactionType": "Sale",
        "transactionDescription": "合成",
        "transactionReasonDescription": "",
        "amountType": "Product Price",
        "amount": 12.34,
        "currency": "USD",
        "totalPayable": None,
        "shipQty": 1,
        "customerOrderNo": "1000",
        "customerOrderLineNo": "1",
        "purchaseOrderNo": "2000",
        "purchaseOrderLineNo": "1",
        "partnerItemId": "3000",
        "partnerGtin": "00000000000001",
        "partnerItemName": "合成商品",
        "fulfillmentType": "Seller Fulfilled",
        "uniqueNo": "u-1",
        "deleteFlag": 0,
        "commissionRate": 15,
        "shipToCity": "合成城市",
        "shipToState": "XX",
        "shipToZipcode": "00000",
        "shipToCountry": "US",
    }
    row.update(overrides)
    return row


def parse(row: dict[str, Any]) -> dict[str, Any]:
    return parse_bill_row(
        row, expected_store_id=STORE, window_start=WINDOW[0], window_end=WINDOW[1]
    )


def test_spec_is_default_off_and_only_the_statement_endpoint() -> None:
    assert WALMART_BILL_SYNC_SPEC.initial_outbound_enabled is False
    assert WALMART_BILL_SYNC_SPEC.schedule_enabled is False
    assert WALMART_BILL_SYNC_SPEC.endpoint_path.endswith("/walmart/bill/statement/list")
    assert WALMART_BILL_SYNC_SPEC.default_page_size == 200


def test_page_needs_code_zero_list_and_total() -> None:
    page = bill_page({"code": 0, "data": {"list": [line()], "totalCount": 1}})
    assert page is not None and page.total_count == 1 and len(page.rows) == 1
    empty = bill_page({"code": 0, "data": {"list": None, "totalCount": 0}})
    assert empty is not None and empty.rows == []
    assert bill_page({"code": 1, "data": {"list": [], "totalCount": 0}}) is None
    assert bill_page({"code": 0, "data": {"list": [1], "totalCount": 1}}) is None
    assert bill_page({"code": 0, "data": {"list": [], "totalCount": -1}}) is None
    assert bill_page({"code": 0, "data": {"list": []}}) is None
    assert bill_page([]) is None


def test_parse_maps_columns_keeps_decimal_and_drops_ship_to() -> None:
    parsed = parse(line())
    assert parsed["lx_line_id"] == "900000000000000123"
    assert parsed["report_id"] == "77"
    assert parsed["amount"] == Decimal("12.3400")
    assert parsed["posted_date"] == date(2026, 10, 5)
    assert parsed["report_date"] == date(2026, 10, 20)
    assert parsed["currency_code"] == "USD"
    assert parsed["total_payable"] is None
    assert parsed["extra_fields"] == {"partnerItemName": "合成商品", "commissionRate": 15}
    assert not any(key.startswith("shipTo") for key in parsed["extra_fields"])


def test_hash_ignores_ship_to_but_sees_amount_changes() -> None:
    assert row_hash(line()) == row_hash(line(shipToCity="别的城市"))
    assert row_hash(line()) != row_hash(line(amount=12.35))


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"storeId": "900000000000000002"}, "SYNC_WALMART_BILL_STORE_MISMATCH"),
        (
            {"transactionPostedTimestamp": "2026-09-30 23:59:59"},
            "SYNC_WALMART_BILL_DATE_OUT_OF_WINDOW",
        ),
        ({"transactionPostedTimestamp": ""}, "SYNC_WALMART_BILL_INVALID_DATE"),
        (
            {"transactionPostedTimestamp": "2026-10-05T00:00:00+08:00"},
            "SYNC_WALMART_BILL_INVALID_DATE",
        ),
        ({"amount": "abc"}, "SYNC_WALMART_BILL_INVALID_AMOUNT"),
        ({"amount": None}, "SYNC_WALMART_BILL_INVALID_AMOUNT"),
        ({"amount": float("nan")}, "SYNC_WALMART_BILL_INVALID_AMOUNT"),
        ({"reportKey": ""}, "SYNC_WALMART_BILL_INVALID_ROW"),
        ({"reportDate": "not-a-date"}, "SYNC_WALMART_BILL_INVALID_DATE"),
        ({"id": "12a"}, "SYNC_WALMART_BILL_INVALID_ROW"),
        ({"deleteFlag": 2}, "SYNC_WALMART_BILL_INVALID_ROW"),
        ({"currency": None}, "SYNC_WALMART_BILL_INVALID_ROW"),
    ],
)
def test_bad_rows_fail_with_a_fixed_code(overrides: dict[str, Any], code: str) -> None:
    with pytest.raises(BillRowError) as error:
        parse(line(**overrides))
    assert error.value.code == code


def test_identity_ignores_ship_to_and_order_but_not_amount_or_type() -> None:
    base = identity_base(line())
    assert identity_base(line(shipToCity="别的城市", partnerItemName="改名")) == base
    assert identity_base(line(amount=12.35)) != base
    assert identity_base(line(amountType="Commission")) != base
    assert identity_base(line(id=900000000000000124)) != base
    assert parse(line())["identity_base"] == base
    assert line_key(base, 1) != line_key(base, 2)


def test_total_payable_is_kept_when_given() -> None:
    assert parse(line(totalPayable="99.5"))["total_payable"] == Decimal("99.5000")


def test_rolling_window_is_35_shanghai_days_and_not_before_march() -> None:
    now = datetime(2026, 11, 8, 17, 0, tzinfo=UTC)  # 上海已经是 11-09
    assert rolling_window(now) == (date(2026, 10, 6), date(2026, 11, 9))
    early = datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
    assert rolling_window(early) == (date(2026, 3, 1), date(2026, 3, 10))


def test_month_segments_split_on_calendar_months() -> None:
    assert month_segments(date(2026, 10, 6), date(2026, 11, 9)) == [
        (date(2026, 10, 6), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 9)),
    ]
    assert month_segments(date(2026, 12, 20), date(2027, 1, 2)) == [
        (date(2026, 12, 20), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 2)),
    ]


def test_period_status() -> None:
    assert period_status(valid_lines=0, payable=Decimal("0")) == "voided"
    assert period_status(valid_lines=3, payable=Decimal("-1")) == "not_payable"
    assert period_status(valid_lines=3, payable=Decimal("0")) == "not_payable"
    assert period_status(valid_lines=3, payable=Decimal("0.01")) == "normal"
