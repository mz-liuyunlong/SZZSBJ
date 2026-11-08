from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.clearance.evaluator import ProductFacts, SalesWindow, evaluate
from app.modules.clearance.rules import ClearanceRules


def w(units: int, days: int, *, profit=0, revenue=100, ads=10, returns=0):
    return SalesWindow(
        units=Decimal(units),
        revenue=Decimal(revenue),
        ads=Decimal(ads),
        profit=Decimal(profit),
        returns=Decimal(returns),
        observed_days=days,
        effective_days=days,
        complete=True,
    )


def facts(*, available=180, listing_days=100, sales7=7, sales14=14, sales30=30):
    return ProductFacts(
        "HK2613",
        "store1",
        "123",
        available,
        listing_days,
        {7: w(sales7, 7), 14: w(sales14, 14), 30: w(sales30, 30)},
    )


def test_rule_defaults_reflect_confirmed_decisions():
    r = ClearanceRules()
    assert r.coverageLookback == 30
    assert r.highCoverage == 180 and r.mediumCoverage == 90 and r.assistCoverage == 60
    assert r.enableNewProductProtection and r.newProductProtectionDays == 60
    assert r.minListingDays == 30 and r.minBusinessSignals == 1
    assert not hasattr(r, "mediumAge")
    assert r.enableRepeatBacklog is False  # Existing reminder flag is retained, not a stock-age rule.


def test_zero_sales_high_overrides_new_product_protection():
    f = facts(available=300, listing_days=35, sales7=0, sales14=0, sales30=0)
    result = evaluate(f, ClearanceRules())
    assert result.level == "high"
    assert any("零销量" in text for text in result.reasons)


def test_missing_sales_is_unknown_not_verified_zero():
    f = ProductFacts("account", "store", "item", 200, 120, {})
    result = evaluate(f, ClearanceRules())
    assert result.level == "unknown"
    assert "zero_sales_30d_evidence" in result.gaps


def test_no_stock_does_not_enter_candidate():
    assert evaluate(facts(available=0), ClearanceRules()).level == "low"


def test_no_stock_data_is_never_zero():
    assert evaluate(facts(available=None), ClearanceRules()).level == "unknown"


def test_new_product_protects_only_medium():
    f = facts(available=120, listing_days=35, sales7=14, sales14=28, sales30=30)
    result = evaluate(f, ClearanceRules())
    assert result.level == "low"
    assert any("新品保护" in reason for reason in result.reasons)
    result2 = evaluate(
        facts(available=900, listing_days=35, sales7=14, sales14=28, sales30=30), ClearanceRules()
    )
    assert result2.level == "high"


def test_profit_conditions_count_as_one_category_even_when_both_trigger():
    f = ProductFacts(
        "account",
        "store",
        "item",
        210,
        95,
        {
            7: w(8, 7, profit=-20, revenue=100),
            14: w(20, 14, profit=-25, revenue=300),
            30: w(40, 30, profit=-50, revenue=500),
        },
    )
    r = ClearanceRules(enableMargin30=True)
    result = evaluate(f, r)
    assert sum(signal["kind"] == "profit" for signal in result.signals) == 1
    assert "持续亏损" in result.signals[0]["reason"]
    assert "30天利润率" in result.signals[0]["reason"]


def test_decline_uses_all_three_configurable_thresholds():
    f = ProductFacts(
        "account",
        "store",
        "item",
        210,
        120,
        {
            7: w(20, 7),
            14: w(70, 14),
            30: w(80, 30),
        },
    )
    result = evaluate(f, ClearanceRules(enableNewProductProtection=False))
    assert any(x["kind"] == "sales_decline" for x in result.signals)
    strict = evaluate(f, ClearanceRules(enableNewProductProtection=False, minSalesDropUnits7=40))
    assert all(x["kind"] != "sales_decline" for x in strict.signals)


def test_new_listings_use_effective_observed_days_not_full_30():
    f = ProductFacts(
        "account",
        "store",
        "item",
        100,
        5,
        {
            7: w(50, 5),
            14: w(50, 5),
            30: w(50, 5),
        },
    )
    result = evaluate(f, ClearanceRules())
    assert result.metrics["sellout_days"] == 10


def test_sellout_thresholds_strictly_ascending():
    with pytest.raises(ValidationError):
        ClearanceRules(assistCoverage=100, mediumCoverage=90, highCoverage=180)


def test_unit_cost_excludes_unrealized_commission_wfs_delivery():
    f = ProductFacts(
        "account",
        "store",
        "item",
        200,
        150,
        {7: w(20, 7), 14: w(40, 14), 30: w(80, 30)},
        unit_inventory_cost_usd=Decimal("6"),
        fulfillment_fee_usd=Decimal("3"),
        commission_rate=Decimal("0.12"),
        current_price_usd=Decimal("20"),
    )
    result = evaluate(f, ClearanceRules(enableFloorPrice=True))
    assert result.metrics["capital_at_cost_usd"] == 1200
    assert result.metrics["unit_full_sale_cost_usd"] == 11.4
    assert result.metrics["unit_margin_usd"] == 8.6
    assert result.metrics["suggested_floor_price_usd"] == 10.23


def test_ad_ratio_requires_negative_recent_profit():
    f = ProductFacts(
        "account",
        "store",
        "item",
        210,
        110,
        {
            7: w(10, 7, profit=5, revenue=100, ads=30),
            14: w(25, 14, profit=20, revenue=300, ads=20),
            30: w(50, 30, profit=30, revenue=1000, ads=50),
        },
    )
    assert not any(x["kind"] == "advertising" for x in evaluate(f, ClearanceRules()).signals)


def test_assisted_risk_requires_stock_coverage_as_well_as_business_signal():
    f = ProductFacts(
        "account",
        "store",
        "item",
        20,
        150,
        {
            7: w(8, 7, profit=-20),
            14: w(20, 14, profit=-25),
            30: w(100, 30, profit=-50),
        },
    )
    r = ClearanceRules(enableNewProductProtection=False)
    result = evaluate(f, r)
    assert any(x["kind"] == "profit" for x in result.signals)
    assert result.level == "low"
