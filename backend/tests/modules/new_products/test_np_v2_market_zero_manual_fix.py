"""Regression: manual V2 scores, protected grades, MART truth, verified zeros."""

from datetime import date, timedelta
from types import SimpleNamespace
from decimal import Decimal

from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from app.modules.new_products.scoring import evaluate
from app.modules.new_products.unified_publish import _reconcile_mart_evidence

CFG = {
    "confirmedScoring": DEFAULT_PARAMETERS,
    "weights": DEFAULT_WEIGHTS,
    "gradeBands": {
        "S": [9, 10],
        "A": [8, 8.99],
        "B": [7, 7.99],
        "C": [6, 6.99],
        "D": [0, 5.99],
    },
}
FIRST = date(2026, 10, 20)
CUTOFF = date(2026, 11, 14)
KEY = ("account", "store", "20858150090")


def _fact(mart_orders=17, mart_units=19, *, daily=None, ad=None):
    return SimpleNamespace(
        daily={
            KEY: daily
            if daily is not None
            else [{"day": FIRST, "order_count": mart_orders, "sales_qty": mart_units}]
        },
        ads={KEY: ad} if ad is not None else {},
    )


def test_mart_daily_deterministic_math_without_fact_agreement():
    f = {
        "first_wfs_available_date_la": FIRST,
        "effective_orders_14d": 9,
        "valid_orders_14d": None,
        "valid_units_14d": None,
        "single_unit_orders_14d": None,
    }
    daily = [{"day": FIRST, "order_count": 9, "sales_qty": 10}]
    _reconcile_mart_evidence(
        f,
        KEY,
        _fact(daily=daily),
        {"sales_units": "10", "ad_spend_usd": "1", "status": "scored"},
        {(KEY[0], KEY[1]): CUTOFF},
        CUTOFF,
    )
    assert (f["valid_orders_14d"], f["valid_units_14d"], f["single_unit_orders_14d"]) == (9, 10, 8)


def test_ambiguous_mart_distribution_never_invents_singles():
    f = {"first_wfs_available_date_la": FIRST, "effective_orders_14d": 7, "valid_orders_14d": None}
    _reconcile_mart_evidence(
        f,
        KEY,
        _fact(daily=[{"day": FIRST, "order_count": 7, "sales_qty": 12}]),
        {"sales_units": "12", "ad_spend_usd": "1", "status": "scored"},
        {(KEY[0], KEY[1]): CUTOFF},
        CUTOFF,
    )
    assert f["valid_orders_14d"] is None


def test_verified_zero_day_rows_are_zero_but_original_financial_metrics_remain_null():
    f = {
        "first_wfs_available_date_la": FIRST,
        "effective_orders_14d": 0,
        "roi": None,
        "gross_margin_pct": None,
        "market_score": None,
    }
    _reconcile_mart_evidence(
        f,
        KEY,
        _fact(daily=[{"day": FIRST, "order_count": 0, "sales_qty": 0}]),
        {"sales_units": "0", "ad_spend_usd": "20", "status": "partial"},
        {(KEY[0], KEY[1]): CUTOFF},
        CUTOFF,
    )
    assert f["zero_sales_verified"] is True
    result = evaluate(f, CFG, 0)
    assert result["dimensions"]["speed"] == "0"
    assert result["dimensions"]["trust"] == "0"
    assert result["dimensions"]["profit"] == "0"
    assert result["total"] is None and result["grade"] is None
    assert f["roi"] is None and f["gross_margin_pct"] is None
    assert evaluate({**f, "market_score": 5}, CFG, 0)["total"] == "0"


def test_no_item_rows_require_store_watermark_and_explicit_zero_paid_sales():
    f = {"first_wfs_available_date_la": FIRST, "effective_orders_14d": None}
    snap = _fact(daily=[])
    _reconcile_mart_evidence(f, KEY, snap, {"sales_units": "0", "status": "partial"}, {}, CUTOFF)
    assert f.get("zero_sales_verified") is not True
    _reconcile_mart_evidence(
        f, KEY, snap, {"sales_units": "0", "status": "partial"}, {(KEY[0], KEY[1]): CUTOFF}, CUTOFF
    )
    assert f["zero_sales_verified"] is True
    assert f["effective_orders_14d"] == 0


def test_verified_no_ad_spend_is_excluded_but_positive_spend_is_not():
    f = {"first_wfs_available_date_la": FIRST}
    _reconcile_mart_evidence(
        f,
        KEY,
        _fact(daily=[]),
        {"status": "scored", "sales_units": "1", "ad_spend_usd": "0"},
        {(KEY[0], KEY[1]): CUTOFF},
        CUTOFF,
    )
    assert f["ad_status"] == "not_run"
    f2 = {"first_wfs_available_date_la": FIRST}
    _reconcile_mart_evidence(
        f2,
        KEY,
        _fact(daily=[]),
        {"status": "scored", "sales_units": "1", "ad_spend_usd": "2"},
        {(KEY[0], KEY[1]): CUTOFF},
        CUTOFF,
    )
    assert f2.get("ad_status") != "not_run"
