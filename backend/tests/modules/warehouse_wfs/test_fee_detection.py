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
