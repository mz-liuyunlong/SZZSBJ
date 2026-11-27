"""Pure new-product risk recommendation rules; no application or DB writes."""

from __future__ import annotations

import copy

import pytest

from app.modules.new_products.risk_conditions import (
    assess_risks,
    default_risk_rules,
    normalize_risk_rules,
)


def edit(rules, code, **changes):
    out = copy.deepcopy(rules)
    row = next(item for item in out if item["code"] == code)
    row.update(changes)
    return out


def facts(**changes):
    values = {
        "profit_calc_status": "scored",
        "gross_margin_pct": "15",
        "ad_status_cumulative": "active",
        "ad_clicks_cumulative": "200",
        "ad_total_spend_usd": "25",
        "ad_orders_cumulative": "5",
        "sales_amount_usd": "300",
    }
    return {**values, **changes}


def test_17_rules_and_manual_none_not_counted():
    r = default_risk_rules()
    assert len(r) == 17
    assert sum(item["source"] == "system" for item in r) == 4
    assert sum(item["source"] == "manual" for item in r) == 13
    assert "无" not in {item["name"] for item in r}


def test_only_confirmed_system_rule_enabled_by_default():
    r = default_risk_rules()
    assert {i["code"] for i in r if i["source"] == "system" and i["enabled"]} == {"low_margin"}


def test_margin_under_ten_caps_to_c_no_score_mutation():
    input_facts = facts(gross_margin_pct="9.9")
    saved = copy.deepcopy(input_facts)
    out = assess_risks(base_grade="A", facts=input_facts)
    assert out["suggested_grade"] == "C"
    assert out["base_grade"] == "A"
    assert input_facts == saved
    assert out["operator_decision"] is None


def test_margin_at_ten_no_cap():
    out = assess_risks(base_grade="A", facts=facts(gross_margin_pct="10"))
    assert out["suggested_grade"] == "A"


def test_missing_profit_proof_does_not_cap():
    result = assess_risks(
        base_grade="A", facts=facts(profit_calc_status="partial", gross_margin_pct="3")
    )
    assert result["suggested_grade"] == "A"
    assert result["risk_evidence_issues"][0]["code"] == "low_margin"


def test_disabled_ads_risks_do_not_apply_even_if_numbers_are_poor():
    result = assess_risks(
        base_grade="A", facts=facts(ad_clicks_cumulative="1", ad_total_spend_usd="1000")
    )
    assert result["suggested_grade"] == "A"


def test_enabled_ad_insufficient_caps_to_b():
    rules = edit(default_risk_rules(), "ad_sample_insufficient", enabled=True)
    out = assess_risks(base_grade="S", facts=facts(ad_clicks_cumulative="19"), risk_rules=rules)
    assert out["suggested_grade"] == "B"
    out = assess_risks(base_grade="S", facts=facts(ad_clicks_cumulative="20"), risk_rules=rules)
    assert out["suggested_grade"] == "S"


def test_unverified_ad_evidence_does_not_trigger():
    rules = edit(default_risk_rules(), "ad_sample_insufficient", enabled=True)
    result = assess_risks(
        base_grade="S",
        facts=facts(ad_status_cumulative="unknown", ad_clicks_cumulative="4"),
        risk_rules=rules,
    )
    assert result["suggested_grade"] == "S"
    assert result["risk_evidence_issues"]


def test_never_advertised_not_treated_as_insufficient_sample():
    rules = edit(default_risk_rules(), "ad_sample_insufficient", enabled=True)
    out = assess_risks(
        base_grade="S",
        facts=facts(ad_status_cumulative="not_run", ad_clicks_cumulative=None),
        risk_rules=rules,
    )
    assert out["suggested_grade"] == "S"


def test_high_spend_ratio_with_confirmed_data():
    rules = edit(default_risk_rules(), "high_ad_spend_ratio", enabled=True)
    out = assess_risks(
        base_grade="A",
        facts=facts(ad_total_spend_usd="30", sales_amount_usd="100"),
        risk_rules=rules,
    )
    assert out["suggested_grade"] == "B"
    out = assess_risks(
        base_grade="A",
        facts=facts(ad_total_spend_usd="25", sales_amount_usd="100"),
        risk_rules=rules,
    )
    assert out["suggested_grade"] == "A"


def test_high_spend_ratio_zero_sales_unverified_not_arbitrary_infinity():
    rules = edit(default_risk_rules(), "high_ad_spend_ratio", enabled=True)
    out = assess_risks(base_grade="A", facts=facts(sales_amount_usd="0"), risk_rules=rules)
    assert out["suggested_grade"] == "A"
    assert out["risk_evidence_issues"]


def test_ads_uncontrolled_disabled_until_admin_enables():
    out = assess_risks(
        base_grade="A",
        facts=facts(ad_clicks_cumulative="200", ad_orders_cumulative="0"),
    )
    assert out["suggested_grade"] == "A"


@pytest.mark.parametrize(
    ("clicks", "orders", "expected"),
    [(99, 0, "A"), (100, 0, "C"), (100, 1, "C"), (100, 2, "A"), (101, 2, "C")],
)
def test_ad_uncontrolled_uses_clicks_and_cvr_exclusively(clicks, orders, expected):
    rules = edit(default_risk_rules(), "ad_uncontrolled", enabled=True)
    result = assess_risks(
        base_grade="A",
        facts=facts(ad_clicks_cumulative=str(clicks), ad_orders_cumulative=str(orders)),
        risk_rules=rules,
    )
    assert result["suggested_grade"] == expected
    if expected == "C":
        evidence = next(x for x in result["risk_hits"] if x["code"] == "ad_uncontrolled")
        assert evidence["observed"]["clicks"] == str(clicks)
        assert "cvr_pct" in evidence["observed"]
        assert "spend" not in evidence["observed"]


def test_ad_uncontrolled_not_affected_by_spend_amount():
    rules = edit(default_risk_rules(), "ad_uncontrolled", enabled=True)
    for spend in ("0", "10000"):
        result = assess_risks(
            base_grade="S",
            facts=facts(
                ad_clicks_cumulative="120", ad_orders_cumulative="1", ad_total_spend_usd=spend
            ),
            risk_rules=rules,
        )
        assert result["suggested_grade"] == "C"


@pytest.mark.parametrize(
    ("clicks", "orders"),
    [(None, "0"), ("100", None), ("100", "101"), ("100.5", "1"), ("100", "1.3")],
)
def test_ad_uncontrolled_missing_or_invalid_evidence_is_not_hit(clicks, orders):
    rules = edit(default_risk_rules(), "ad_uncontrolled", enabled=True)
    result = assess_risks(
        base_grade="A",
        facts=facts(ad_clicks_cumulative=clicks, ad_orders_cumulative=orders),
        risk_rules=rules,
    )
    assert result["suggested_grade"] == "A"
    assert any(x["code"] == "ad_uncontrolled" for x in result["risk_evidence_issues"])


def test_strictest_risk_cap_wins_without_upgrading_d():
    rules = edit(default_risk_rules(), "high_ad_spend_ratio", enabled=True)
    for grade, expected in [("A", "C"), ("D", "D")]:
        result = assess_risks(
            base_grade=grade,
            facts=facts(gross_margin_pct="8", ad_total_spend_usd="90", sales_amount_usd="100"),
            risk_rules=rules,
        )
        assert result["suggested_grade"] == expected


def test_manual_selected_risk_caps_and_flag_independently():
    out = assess_risks(
        base_grade="S", facts=facts(), manual_selected=["ROI低（评级上限）", "侵权风险"]
    )
    assert out["suggested_grade"] == "B"
    assert out["recommend_not_pass"] is True
    assert out["operator_decision"] is None


def test_manual_none_means_no_manual_risk():
    out = assess_risks(base_grade="B", facts=facts(), manual_selected=["无"])
    assert not any(r["source"] == "manual" for r in out["risk_hits"])


@pytest.mark.parametrize("codes", [["无", "侵权风险"], ["侵权风险", "侵权风险"], ["不存在"]])
def test_manual_invalid_selections_fail_closed(codes):
    with pytest.raises(ValueError):
        assess_risks(base_grade="A", facts=facts(), manual_selected=codes)


def test_unknown_and_duplicate_config_fails_closed():
    rules = default_risk_rules()
    rules[0]["code"] = "unknown"
    with pytest.raises(ValueError):
        normalize_risk_rules(rules)
    rules = default_risk_rules()
    rules[-1]["code"] = rules[0]["code"]
    with pytest.raises(ValueError):
        normalize_risk_rules(rules)


def test_legacy_missing_config_provides_defaults_without_mutating_source():
    rules = default_risk_rules()
    copy_before = copy.deepcopy(rules)
    assert normalize_risk_rules(rules) == copy_before
    assert rules == copy_before
    assert len(normalize_risk_rules(None)) == 17


def test_non_finite_margin_never_produces_cap():
    out = assess_risks(base_grade="A", facts=facts(gross_margin_pct="NaN"))
    assert out["suggested_grade"] == "A"
    assert out["risk_evidence_issues"]


def test_legacy_18_items_read_without_changing_saved_history():
    original = default_risk_rules()
    legacy = copy.deepcopy(original)
    legacy.insert(
        5,
        {
            "code": "ad_sudden_change",
            "name": "广告数据骤变",
            "source": "manual",
            "enabled": True,
            "limit": "none",
            "params": {},
        },
    )
    saved = copy.deepcopy(legacy)
    normalized = normalize_risk_rules(legacy)
    assert normalized == original
    assert legacy == saved
    assert all(r["code"] != "ad_sudden_change" for r in normalized)


def test_deleted_manual_risk_cannot_be_newly_selected():
    with pytest.raises(ValueError):
        assess_risks(base_grade="A", facts=facts(), manual_selected=["广告数据骤变"])
