from datetime import date
from decimal import Decimal

import pytest

from app.modules.warehouse_wfs.fee_detection import (
    SettlementFeeRow,
    is_wfs_overcharge,
    resolve_wfs_fees,
)


def make_row(
    *,
    store="store-a",
    order="order-1",
    qty="0",
    fee="0",
    date="2026-10-01",
    line="line-1",
):
    return SettlementFeeRow(
        source_account_ref="account-a",
        store_id=store,
        msku="TEST-SKU",
        platform_order_no=order,
        sales_num=Decimal(qty),
        platform_logistics_amount=Decimal(fee),
        settlement_date=date,
        source_line_ref=line,
    )


def test_order_fee_row_pairs_with_sales_row():
    rows = [
        make_row(qty="10", fee="0", line="sales"),
        make_row(qty="0", fee="-46.50", line="fee"),
    ]
    result = resolve_wfs_fees(rows)
    assert len(result) == 1
    assert result[0].unit_fee == Decimal("4.65")
    assert result[0].sample_units == Decimal("10")
    assert result[0].fee_orders == 1


def test_insufficient_units_returns_none():
    result = resolve_wfs_fees(
        [
            make_row(qty="3", fee="-12.00"),
        ]
    )
    assert result[0].unit_fee is None


def test_stores_are_independent():
    result = resolve_wfs_fees(
        [
            make_row(store="store-a", qty="10", fee="-40", line="a"),
            make_row(store="store-b", qty="10", fee="-60", line="b"),
        ]
    )
    assert len(result) == 2
    assert [item.unit_fee for item in result] == [
        Decimal("4.00"),
        Decimal("6.00"),
    ]


def test_mode_tie_uses_latest_settlement_date():
    result = resolve_wfs_fees(
        [
            make_row(order="a", qty="5", fee="-20", date="2026-09-01", line="a"),
            make_row(order="b", qty="5", fee="-25", date="2026-10-01", line="b"),
        ]
    )
    assert result[0].unit_fee == Decimal("5.00")


def test_overcharge_requires_both_fees():
    assert is_wfs_overcharge(
        actual_unit_fee=Decimal("5.18"),
        standard_unit_fee=Decimal("4.65"),
    )
    assert not is_wfs_overcharge(
        actual_unit_fee=None,
        standard_unit_fee=Decimal("4.65"),
    )
    assert not is_wfs_overcharge(
        actual_unit_fee=Decimal("4.65"),
        standard_unit_fee=Decimal("4.65"),
    )


def test_duplicate_source_line_rejected():
    with pytest.raises(ValueError, match="WFS_DUPLICATE"):
        resolve_wfs_fees(
            [
                make_row(qty="5", line="same"),
                make_row(qty="5", line="same"),
            ]
        )


def test_missing_order_identity_is_rejected_instead_of_grouping_by_line():
    with pytest.raises(ValueError, match="WFS_MISSING_ORDER_IDENTITY"):
        resolve_wfs_fees([make_row(order="", qty="10", fee="-40")])


def test_mode_counts_orders_not_units() -> None:
    result = resolve_wfs_fees(
        [
            make_row(order="large", qty="20", fee="-125.20", line="large"),
            make_row(order="small-a", qty="1", fee="-6.95", line="small-a"),
            make_row(order="small-b", qty="1", fee="-6.95", line="small-b"),
        ]
    )[0]

    assert result.unit_fee == Decimal("6.95")
    assert result.mode_count == 2
    assert result.sample_units == Decimal("22")
    assert result.fee_orders == 3


def test_units_from_zero_fee_or_unpaired_orders_are_not_valid_samples() -> None:
    result = resolve_wfs_fees(
        [
            make_row(order="zero-fee", qty="100", fee="0", line="zero"),
            make_row(order="valid", qty="10", fee="-69.50", line="valid"),
        ]
    )[0]

    assert result.sample_units == Decimal("10")
    assert result.fee_orders == 1


def test_verified_sixty_day_regression_uses_order_mode_not_unit_weight() -> None:
    rows = []
    for index in range(32):
        units = 2 if index < 6 else 1
        rows.append(
            make_row(
                order=f"high-{index}",
                qty=str(units),
                fee=str(Decimal("-6.95") * units),
                date="2026-09-23",
                line=f"high-{index}",
            )
        )
    for index in range(22):
        units = 2 if index < 2 else 1
        rows.append(
            make_row(
                order=f"low-{index}",
                qty=str(units),
                fee=str(Decimal("-6.26") * units),
                date="2026-08-24",
                line=f"low-{index}",
            )
        )

    result = resolve_wfs_fees(rows)[0]

    assert result.sample_units == Decimal("62")
    assert result.fee_orders == 54
    assert result.mode_count == 32
    assert result.unit_fee == Decimal("6.95")
    assert result.latest_settlement_date == date(2026, 9, 23)
