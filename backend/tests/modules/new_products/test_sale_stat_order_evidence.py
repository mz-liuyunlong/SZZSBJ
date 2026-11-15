from datetime import date, timedelta
from decimal import Decimal

from app.modules.new_products.sale_stat_order_evidence import (
    reconcile_sale_stat_order_evidence as reconcile,
)

DAY = date(2026, 10, 9)


def row(day, orders, units):
    return {"day": day, "order_count": orders, "sales_qty": units}


def fact(orders, units, singles, unknown=0):
    return {
        "order_count": orders,
        "units": units,
        "single_orders": singles,
        "unknown_lines": unknown,
    }


def test_yc00656_mart_17_fact_10_first_order_day_3():
    x = reconcile(
        first_wfs_day=DAY,
        daily_rows=[row(DAY + timedelta(days=2), 1, 1), row(DAY + timedelta(days=5), 16, 18)],
        canonical_orders=fact(10, 11, 9),
    )
    assert (x.effective_orders, x.first_order_day, x.valid_orders, x.fact_reconciled) == (
        17,
        3,
        None,
        False,
    )


def test_yc00738_historical_only_has_no_false_trust():
    x = reconcile(
        first_wfs_day=DAY,
        daily_rows=[row(DAY + timedelta(days=2), 19, 25)],
        canonical_orders=fact(0, None, 0),
    )
    assert x.effective_orders == 19 and x.valid_orders is None


def test_yc00697_does_not_fabricate_trust():
    x = reconcile(
        first_wfs_day=DAY, daily_rows=[row(DAY, 13, 15)], canonical_orders=fact(11, 13, 10)
    )
    assert x.effective_orders == 13 and x.valid_units is None


def test_fact_greater_than_mart_never_blocks_speed_but_blocks_trust():
    for facts in [fact(6, 6, 6), fact(18, 20, 16)]:
        x = reconcile(
            first_wfs_day=DAY,
            daily_rows=[
                row(
                    DAY,
                    5 if facts["order_count"] == 6 else 17,
                    5 if facts["order_count"] == 6 else 19,
                )
            ],
            canonical_orders=facts,
        )
        assert x.effective_orders == (5 if facts["order_count"] == 6 else 17)
        assert x.first_order_day == 1
        assert x.valid_orders is None and x.single_orders is None and not x.fact_reconciled


def test_exact_match_keeps_trust():
    x = reconcile(first_wfs_day=DAY, daily_rows=[row(DAY, 9, 10)], canonical_orders=fact(9, 10, 8))
    assert (
        x.effective_orders,
        x.valid_orders,
        x.valid_units,
        x.single_orders,
        x.fact_reconciled,
    ) == (9, 9, Decimal(10), 8, True)


def test_no_mart_fails_closed():
    x = reconcile(first_wfs_day=DAY, daily_rows=[], canonical_orders=fact(10, 11, 9))
    assert x.effective_orders is None and x.valid_orders is None


def test_bad_mart_fails_closed():
    for orders, units in [(-1, 1), (1, -1), (Decimal("1.5"), 2), (None, 1), ("NaN", 1)]:
        x = reconcile(
            first_wfs_day=DAY, daily_rows=[row(DAY, orders, units)], canonical_orders=fact(0, 0, 0)
        )
        assert x.effective_orders is None


def test_missing_start_day_fails_closed():
    x = reconcile(first_wfs_day=None, daily_rows=[row(DAY, 1, 1)], canonical_orders=fact(1, 1, 1))
    assert x.effective_orders is None


def test_invalid_observation_date_fails_closed():
    for day in [DAY - timedelta(days=1), DAY + timedelta(days=14)]:
        x = reconcile(
            first_wfs_day=DAY, daily_rows=[row(day, 1, 1)], canonical_orders=fact(1, 1, 1)
        )
        assert x.effective_orders is None


def test_zero_sales_rows_are_not_confused_with_missing_rows():
    x = reconcile(first_wfs_day=DAY, daily_rows=[row(DAY, 0, 0)], canonical_orders=fact(0, 0, 0))
    assert x.effective_orders == 0 and x.first_order_day is None


def test_unknown_fact_leaves_trust_unavailable():
    x = reconcile(
        first_wfs_day=DAY, daily_rows=[row(DAY, 4, 4)], canonical_orders=fact(4, 4, 4, unknown=2)
    )
    assert x.effective_orders == 4 and x.valid_orders is None


def test_msku_rows_same_item_are_aggregated():
    x = reconcile(
        first_wfs_day=DAY,
        daily_rows=[row(DAY, 4, 4), row(DAY, 5, 5)],
        canonical_orders=fact(9, 9, 9),
    )
    assert x.effective_orders == 9 and x.fact_reconciled


def test_fact_units_greater_than_mart_blocks_trust_not_speed():
    x = reconcile(
        first_wfs_day=DAY, daily_rows=[row(DAY, 17, 19)], canonical_orders=fact(10, 20, 9)
    )
    assert x.effective_orders == 17 and x.first_order_day == 1
    assert x.valid_orders is None and x.single_orders is None


def test_fact_malformed_does_not_block_paid_sales_score():
    x = reconcile(
        first_wfs_day=DAY,
        daily_rows=[row(DAY, 17, 19)],
        canonical_orders={"order_count": "oops", "units": 19, "single_orders": 10},
    )
    assert x.effective_orders == 17 and x.valid_orders is None


# Production READ ONLY audit of 2026-11-14: all fourteen conflicting identities.
# These cases protect the source boundary, not a production data rewrite.
import pytest


@pytest.mark.parametrize(
    "sku,mart_orders,mart_units,fact_orders,fact_units,expected",
    [
        ("YC00738", 19, 25, 0, 0, 19),
        ("YC00665", 19, 19, 9, 9, 19),
        ("YC00656", 17, 19, 10, 11, 17),
        ("YC00723", 8, 8, 1, 1, 8),
        ("YC00657", 7, 7, 2, 2, 7),
        ("YC00711", 4, 6, 0, 0, 4),
        ("YC00726", 17, 19, 13, 15, 17),
        ("YC00740", 9, 9, 5, 5, 9),
        ("YC00663", 9, 10, 6, 7, 9),
        ("YC00697", 13, 15, 11, 13, 13),
        ("YC00672", 2, 2, 1, 1, 2),
        ("YC00718", 1, 1, 0, 0, 1),
        ("YC00704", 5, 5, 6, 6, 5),
        ("YC00775", 17, 19, 18, 20, 17),
    ],
)
def test_all_conflicting_skus_preserve_mart_speed_and_block_unverified_trust(
    sku, mart_orders, mart_units, fact_orders, fact_units, expected
):
    x = reconcile(
        first_wfs_day=DAY,
        daily_rows=[row(DAY, mart_orders, mart_units)],
        canonical_orders=fact(fact_orders, fact_units, 0),
    )
    assert x.effective_orders == expected, sku
    assert x.valid_orders is None, sku
    assert x.valid_units is None, sku
    assert x.single_orders is None, sku
