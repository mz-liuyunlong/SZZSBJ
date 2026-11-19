"""PR337 verified metrics never convert missing evidence to zeros."""

from datetime import date
from decimal import Decimal

from app.modules.new_products.compute import (
    calculate,
    summarize_ad,
    summarize_daily,
    summarize_refunds,
)


def test_missing_sources_remain_null():
    assert summarize_daily([])["sales_units"] is None
    assert summarize_ad({}, None)["ad_spend_usd"] is None
    assert summarize_refunds([], None, None)["returned_units"] is None


def test_known_usd_sales_and_profit():
    metrics = summarize_daily([
        {
            "sales_qty": Decimal("3"),
            "order_count": 2,
            "sales_amount": Decimal("24"),
            "sales_currency_code": "USD",
            "cost_status": "complete",
            "gross_profit_amount": Decimal("6"),
            "gross_profit_currency_code": "USD",
            "purchase_cost_total_usd": Decimal("7"),
            "first_leg_cost_total_usd": Decimal("3"),
        }
    ])
    assert metrics["sales_units"] == 3
    assert metrics["sales_orders"] == 2
    assert metrics["profit_usd"] == 6
    assert metrics["roi"] == Decimal("0.6")
    assert metrics["profit_margin_pct"] == 25


def test_foreign_currency_cannot_be_presented_as_usd():
    metrics = summarize_daily([
        {
            "sales_qty": 2,
            "order_count": 1,
            "sales_amount": 50,
            "sales_currency_code": "CNY",
            "cost_status": "partial",
            "gross_profit_amount": None,
            "gross_profit_currency_code": None,
        }
    ])
    assert metrics["sales_amount_usd"] is None
    assert metrics["profit_usd"] is None


def test_refund_rates_use_original_cohort():
    rows = [
        {"return_order_id": "R1", "return_qty": 1, "reason_code": "SIZE"},
        {"return_order_id": "R1", "return_qty": 1, "reason_code": "SIZE"},
        {"return_order_id": "R2", "return_qty": 1, "reason_code": "OTHER"},
    ]
    output = summarize_refunds(rows, Decimal("10"), 5)
    assert output["returned_units"] == 3
    assert output["returned_orders"] == 2
    assert output["return_rate_units_pct"] == 30
    assert output["return_rate_orders_pct"] == 40


def test_apply_is_not_default():
    assert calculate.__kwdefaults__ == {"apply": False}
    assert date.fromisoformat("2026-11-12").isoformat() == "2026-11-12"
