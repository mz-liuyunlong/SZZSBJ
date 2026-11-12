"""Pure business rules tests; synthetic facts are never exposed as operational data."""

from copy import deepcopy
from decimal import Decimal

from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS, validate
from app.modules.new_products.scoring import evaluate


def config():
    return {
        "weights": deepcopy(DEFAULT_WEIGHTS),
        "confirmedScoring": deepcopy(DEFAULT_PARAMETERS),
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
        "quantities": {
            "S": [400, 600],
            "A": [300, 500],
            "B": [200, 400],
            "C": [150, 250],
            "D": [0, 0],
            "Pass": [0, 0],
        },
        "scoreCriteria": {"market": [""] * 5},
        "penalties": [],
        "vetoes": [
            {"name": "ROI 低（Pass）", "enabled": True},
            {"name": "ROI 低（评级上限）", "enabled": True},
            {"name": "毛利率过低", "enabled": True},
        ],
    }


def facts():
    return {
        "market_score": 7,
        "first_order_day": 3,
        "elapsed_days": 14,
        "effective_orders_14d": 20,
        "valid_orders_14d": 20,
        "valid_units_14d": 20,
        "single_unit_orders_14d": 18,
        "ad_status": "active",
        "ad_spend_usd": Decimal("20"),
        "ad_clicks": 20,
        "ad_orders": 1,
        "ad_revenue_usd": Decimal("20") / Decimal(".29"),
        "roi": Decimal("1"),
        "gross_margin_pct": Decimal("17.5"),
    }


def test_confirmed_parameters_are_valid():
    assert validate("performance", config())


def test_confirmed_thresholds_and_weighted_scores():
    r = evaluate(facts(), config(), 1)
    assert r["dimensions"]["speed"] == "10"
    assert Decimal(r["dimensions"]["ad"]).quantize(Decimal(".01")) == Decimal("6.95")
    assert Decimal(r["dimensions"]["profit"]) == Decimal("5.00")
    assert r["dimensions"]["trust"] == "10"
    assert r["total"] is not None


def test_no_ad_is_not_implied_by_missing_ad_data():
    f = facts()
    f.update(
        ad_status="unknown", ad_spend_usd=None, ad_orders=None, ad_clicks=None, ad_revenue_usd=None
    )
    r = evaluate(f, config(), 1)
    assert r["grade"] is None and r["total"] is None
    assert r["ad_excluded"] is False


def test_verified_no_ads_reweights_remaining_dimensions():
    f = facts()
    f.update(
        ad_status="not_run", ad_spend_usd=None, ad_orders=None, ad_clicks=None, ad_revenue_usd=None
    )
    r = evaluate(f, config(), 1)
    assert r["ad_excluded"] is True
    assert r["total"] is not None


def test_no_ads_and_no_orders_is_continue_observation_not_pass():
    f = facts()
    f.update(
        market_score=7,
        ad_status="not_run",
        elapsed_days=14,
        effective_orders_14d=0,
        valid_orders_14d=0,
        valid_units_14d=0,
        single_unit_orders_14d=0,
        first_order_day=None,
        roi=None,
        gross_margin_pct=None,
    )
    r = evaluate(f, config(), 1)
    assert r["observation_state"] == "continue_observation"
    assert r["grade"] is None


def test_paid_ads_without_conversion_zero_acos_cvr_and_cpc_counts():
    f = facts()
    f.update(ad_spend_usd=Decimal("12"), ad_clicks=15, ad_orders=0, ad_revenue_usd=0)
    r = evaluate(f, config(), 1)
    assert r["dimensions"]["ad"] == "2"


def test_roi_veto_and_cap():
    f = facts()
    f["roi"] = Decimal(".49")
    assert evaluate(f, config(), 1)["grade"] == "Pass"
    f["roi"] = Decimal(".79")
    assert evaluate(f, config(), 1)["grade"] in ["B", "C", "D"]


def test_missing_market_blocks_final_rating():
    f = facts()
    f["market_score"] = None
    assert evaluate(f, config(), 1)["grade"] is None
