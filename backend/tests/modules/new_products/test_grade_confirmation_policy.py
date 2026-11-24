from datetime import date

from app.modules.new_products.evaluation_policy import evaluation_status
from app.modules.new_products.risk_conditions import default_risk_rules
from app.modules.new_products.risk_display import build_saved_risk_display


def test_grade_status_pending_confirmed_legacy():
    common = dict(listing_date=None, first_wfs=date(2026, 11, 1), grade="B", total="7.3")
    pending = {"evaluation_grade_confirmation_v1": {"status": "pending"}}
    confirmed = {"evaluation_grade_confirmation_v1": {"status": "confirmed"}}
    assert evaluation_status(coverage=pending, **common) == "待等级确认"
    assert evaluation_status(coverage=confirmed, **common) == "待测评确认"
    assert evaluation_status(coverage={}, **common) == "待测评确认"


def test_verified_partial_campaign_split_can_use_grand_totals():
    rules = default_risk_rules()
    for rule in rules:
        if rule["source"] == "system":
            rule["enabled"] = True
    coverage = {
        "ad_display_v1": {
            "source": "fact_walmart_ad_item_sp_daily",
            "status": "classification_incomplete",
            "window_start_la": "2026-11-01",
            "window_end_la": "2026-11-18",
            "source_campaigns": 2,
            "invalid_campaigns": 0,
            "facts": {
                "ad_total_spend_usd": "60",
                "ad_total_clicks": "120",
                "ad_total_orders": "1",
            },
        },
        "new_products_testing_profit_v2": {
            "through_la": "2026-11-18",
            "status": "scored",
            "policy": "returns_ignored_samples_excluded_sample_ads_included",
            "missing": [],
            "gross_margin_pct": "8",
            "sales_amount_usd": "100",
            "ad_spend_usd": "30",
        },
    }
    result = build_saved_risk_display(
        coverage,
        rules,
        cutoff_la=date(2026, 11, 18),
        first_wfs=date(2026, 11, 1),
        rule_version=2,
    )
    states = {r["code"]: r["status"] for r in result["rules"]}
    assert states == {
        "ad_sample_insufficient": "clear",
        "ad_uncontrolled": "hit",
        "low_margin": "hit",
        "high_ad_spend_ratio": "hit",
    }
    coverage["ad_display_v1"]["invalid_campaigns"] = 1
    invalid = build_saved_risk_display(
        coverage,
        rules,
        cutoff_la=date(2026, 11, 18),
        first_wfs=date(2026, 11, 1),
        rule_version=2,
    )
    statuses = {r["code"]: r["status"] for r in invalid["rules"]}
    assert statuses["ad_uncontrolled"] == "unverified"
    assert statuses["low_margin"] == "hit"
