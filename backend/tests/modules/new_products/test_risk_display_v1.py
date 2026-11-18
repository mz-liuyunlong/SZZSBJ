"""Risk display must not present incomplete, stale or frozen evidence as hits."""

from copy import deepcopy
from datetime import date

from app.modules.new_products.risk_conditions import default_risk_rules
from app.modules.new_products.risk_display import build_saved_risk_display

CUT = date(2026, 11, 17)


def config(*enabled):
    r = default_risk_rules()
    for item in r:
        if item["source"] == "system":
            item["enabled"] = item["code"] in enabled
    return r


def coverage(
    *,
    spend="90",
    clicks="120",
    orders="1",
    margin="8",
    revenue="200",
    adspend="60",
    cutoff="2026-11-17",
):
    return {
        "ad_display_v1": {
            "status": "complete",
            "window_start_la": "2026-10-10",
            "window_end_la": cutoff,
            "facts": {
                "ad_total_spend_usd": spend,
                "ad_total_clicks": clicks,
                "ad_total_orders": orders,
            },
        },
        "new_products_testing_profit_v2": {
            "through_la": cutoff,
            "status": "scored",
            "policy": "returns_ignored_samples_excluded_sample_ads_included",
            "missing": [],
            "gross_margin_pct": margin,
            "sales_amount_usd": revenue,
            "ad_spend_usd": adspend,
        },
    }


def result(cov, rules):
    res = build_saved_risk_display(
        cov, rules, cutoff_la=CUT, first_wfs="2026-10-10", rule_version=9
    )
    return {x["code"]: x for x in res["rules"]}


def test_hit_uncontrolled_and_margin_and_ratio():
    r = result(coverage(), config("ad_uncontrolled", "low_margin", "high_ad_spend_ratio"))
    assert r["ad_uncontrolled"]["status"] == "hit"
    assert "120" in r["ad_uncontrolled"]["basis"] and "0.83" in r["ad_uncontrolled"]["basis"]
    assert r["ad_uncontrolled"]["limit"] == "C"
    assert r["low_margin"]["status"] == "hit" and r["low_margin"]["limit"] == "C"
    assert r["high_ad_spend_ratio"]["status"] == "hit"
    assert "30%" in r["high_ad_spend_ratio"]["basis"]


def test_not_hit_with_verified_data():
    r = result(
        coverage(clicks="120", orders="10", margin="18", adspend="20"),
        config("ad_sample_insufficient", "ad_uncontrolled", "low_margin", "high_ad_spend_ratio"),
    )
    assert all(x["status"] == "clear" for x in r.values())


def test_insufficient_sample_requires_ads():
    r = result(coverage(clicks="19", orders="0", spend="10"), config("ad_sample_insufficient"))
    assert r["ad_sample_insufficient"]["status"] == "hit"
    r = result(coverage(clicks="0", orders="0", spend="0"), config("ad_sample_insufficient"))
    assert r["ad_sample_insufficient"]["status"] == "clear"


def test_missing_or_old_ads_not_a_hit():
    cov = coverage()
    cov["ad_display_v1"]["status"] = "classification_incomplete"
    r = result(cov, config("ad_uncontrolled"))
    assert r["ad_uncontrolled"]["status"] == "unverified"
    cov = coverage(cutoff="2026-11-16")
    r = result(cov, config("ad_uncontrolled", "low_margin"))
    assert r["ad_uncontrolled"]["status"] == "unverified"
    assert r["low_margin"]["status"] == "unverified"


def test_profit_snapshot_independent_of_ads():
    cov = coverage()
    cov.pop("ad_display_v1")
    r = result(cov, config("ad_uncontrolled", "low_margin"))
    assert r["ad_uncontrolled"]["status"] == "unverified"
    assert r["low_margin"]["status"] == "hit"


def test_bad_profit_policy_fails_closed():
    cov = coverage()
    cov["new_products_testing_profit_v2"]["policy"] = "unverified"
    r = result(cov, config("low_margin", "high_ad_spend_ratio"))
    assert r["low_margin"]["status"] == "unverified"
    assert r["high_ad_spend_ratio"]["status"] == "unverified"


def test_disabled_never_auto_checks():
    r = result(coverage(), config())
    assert all(x["status"] == "disabled" for x in r.values())


def test_old_frozen_snapshot_fails_closed():
    cov = coverage()
    cov["evaluation_final_snapshot"] = {"grade": "A", "total": "8.5"}
    r = result(cov, config("ad_uncontrolled", "low_margin"))
    assert r["low_margin"]["status"] == "unverified"
    assert r["ad_uncontrolled"]["status"] == "unverified"


def test_missing_config_cannot_use_default_enabled_rule():
    r = result(coverage(), None)
    assert r["low_margin"]["status"] == "unverified"


def test_no_mutations():
    data = coverage()
    rules = config("ad_uncontrolled", "low_margin")
    d2 = deepcopy(data)
    r2 = deepcopy(rules)
    build_saved_risk_display(data, rules, cutoff_la=CUT, first_wfs="2026-10-10", rule_version=9)
    assert data == d2 and rules == r2


def test_wrong_first_wfs_date_cannot_auto_check():
    output = build_saved_risk_display(
        coverage(),
        config("ad_uncontrolled", "low_margin"),
        cutoff_la=CUT,
        first_wfs="2026-10-11",
        rule_version=9,
    )
    risks = {r["code"]: r for r in output["rules"]}
    assert risks["ad_uncontrolled"]["status"] == "unverified"
    assert risks["low_margin"]["status"] == "hit"
    assert output["rule_version"] == 9


def test_missing_first_wfs_blocks_all():
    output = build_saved_risk_display(
        coverage(),
        config("ad_uncontrolled", "low_margin"),
        cutoff_la=CUT,
        first_wfs=None,
        rule_version=9,
    )
    assert all(x["status"] == "unverified" for x in output["rules"] if x["enabled"])
