"""Pure V1 clearance rule regressions: no database or upstream APIs required."""

from datetime import date

import pytest

from app.modules.clearance_center.rules import DEFAULT_RULES, evaluate, validate_rules

TODAY = date(2026, 11, 4)


def listing(qty: int = 150, *, rating: float = 4.5):
    return {"wfs_available_quantity": qty, "average_rating": rating, "review_count": 30}


def metrics(sales: int = 30, **overrides):
    baseline = {
        "sales30": sales,
        "sales7": 5,
        "prev7": 5,
        "revenue30": 300,
        "revenue7": 70,
        "revenue_prev7": 70,
        "profit30": 50,
        "profit7": 5,
        "profit_prev7": 5,
        "ad7": 5,
        "ad_prev7": 5,
        "refund_qty": 0,
        "positive_stock_days": 25,
        "inventory_fresh": True,
        "sales_complete": True,
        "cost_complete": True,
        "listing_days": 100,
    }
    baseline.update(overrides)
    return baseline


def check(stock: int, sales: int, **overrides):
    return evaluate(listing(stock), metrics(sales, **overrides), DEFAULT_RULES, as_of=TODAY)


def test_high_backlog_without_business_signal():
    result = check(200, 30)
    assert result["risk_level"] == "high"
    assert result["candidate_status"] == "auto"
    assert result["coverage_days"] == 200
    assert result["suggested_qty"] == 140


def test_medium_coverage_requires_business_signal():
    result = check(120, 30)
    assert result["risk_level"] == "low"
    assert result["candidate_status"] == "observe"
    result = check(120, 30, profit30=10, revenue30=300)
    assert result["risk_level"] == "medium"
    assert result["candidate_status"] == "auto"


def test_assisted_coverage_needs_two_distinct_groups():
    only_profit = check(75, 30, profit30=-5, profit7=-1, profit_prev7=-1)
    assert only_profit["risk_level"] == "low"
    assert only_profit["business_signal_groups"] == ["PROFIT"]
    with_sales = check(75, 30, profit30=-5, profit7=-1, profit_prev7=-1, sales7=2, prev7=20)
    assert with_sales["risk_level"] == "medium"
    assert with_sales["business_signal_groups"] == ["PROFIT", "SALES"]


def test_sales_drop_requires_prior_sample_and_absolute_drop():
    result = check(120, 30, sales7=3, prev7=5)
    assert "SALES" not in result["business_signal_groups"]
    result = check(120, 30, sales7=6, prev7=11)
    assert "SALES" in result["business_signal_groups"]


def test_ads_compare_nonoverlapping_windows_and_require_loss():
    base = dict(
        sales7=5,
        prev7=10,
        ad7=20,
        ad_prev7=5,
        revenue7=100,
        revenue_prev7=100,
        profit7=-2,
        profit_prev7=5,
    )
    result = check(75, 30, profit30=40, **base)
    assert "ADS" in result["business_signal_groups"]
    result = check(75, 30, profit30=40, **{**base, "profit7": 2})
    assert "ADS" not in result["business_signal_groups"]


def test_no_auto_entry_without_backlog():
    result = check(20, 30, profit30=-100, refund_qty=6, profit7=-30, profit_prev7=-10)
    assert result["candidate_status"] != "auto"


def test_verified_zero_sales_requires_21_positive_stock_days():
    result = check(40, 0, positive_stock_days=21)
    assert result["risk_level"] == "high"
    assert result["suggested_qty"] == 40
    result = check(40, 0, positive_stock_days=3)
    assert result["risk_level"] != "high"
    assert result["candidate_status"] != "auto"


def test_sales_missing_never_becomes_verified_zero():
    result = check(40, 0, sales_complete=False)
    assert result["risk_level"] != "high"
    assert result["suggested_qty"] is None


def test_protection_preserves_high_risk():
    result = check(200, 30, listing_days=10)
    assert result["risk_level"] == "high"
    assert result["candidate_status"] == "auto"


def test_new_listing_and_recovery_protect_medium_only():
    result = check(120, 30, listing_days=10, profit30=1)
    assert result["risk_level"] == "medium"
    assert result["candidate_status"] == "observe"
    assert "NEW_LISTING_PROTECTION" in result["protections"]
    result = check(120, 30, listing_days=70, profit30=1, prev7=5, sales7=8)
    assert result["risk_level"] == "medium"
    assert result["candidate_status"] == "observe"


def test_missing_cost_cannot_trigger_profit_signals():
    result = check(75, 30, cost_complete=False, profit30=-30, profit7=-5, profit_prev7=-5)
    assert "PROFIT" not in result["business_signal_groups"]


def test_qty_zero_with_safety_stock_never_negative():
    r = {**DEFAULT_RULES, "safety_stock_units": 50}
    value = evaluate(listing(40), metrics(0), r, as_of=TODAY)
    assert value["suggested_qty"] == 0


def test_rules_reject_invalid_threshold_order():
    with pytest.raises(ValueError):
        validate_rules({"medium_coverage_days": 190})
    with pytest.raises(ValueError):
        validate_rules({"unknown_field": 1})
