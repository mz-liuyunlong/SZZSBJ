from datetime import date

import pytest

from app.modules.new_products.risk_conditions import default_risk_rules
from app.modules.new_products.risk_finalization import resolve_final_risks

POLICY = "returns_ignored_samples_excluded_sample_ads_included"
CUTOFF = date(2026, 11, 22)
FIRST = date(2026, 11, 1)


def coverage(clicks=110, orders=1, margin=8, spend=30):
    return {
        "ad_display_v1": {
            "source": "fact_walmart_ad_item_sp_daily",
            "status": "complete",
            "window_start_la": str(FIRST),
            "window_end_la": str(CUTOFF),
            "facts": {
                "ad_total_spend_usd": str(spend),
                "ad_total_clicks": clicks,
                "ad_total_orders": orders,
            },
        },
        "new_products_testing_profit_v2": {
            "through_la": str(CUTOFF),
            "status": "scored",
            "policy": POLICY,
            "missing": [],
            "gross_margin_pct": str(margin),
            "sales_amount_usd": "100",
            "ad_spend_usd": str(spend),
        },
    }


def run(selected=None, enabled=(), **facts):
    rules = default_risk_rules()
    for rule in rules:
        if rule["source"] == "system":
            rule["enabled"] = rule["code"] in enabled
    return resolve_final_risks(
        coverage=coverage(**facts),
        config={"riskConditions": rules},
        rule_version=3,
        base_grade="S",
        manual_selected=selected or ["无"],
        cutoff=CUTOFF,
        first_wfs=FIRST,
    )


@pytest.mark.parametrize(
    ("code", "facts", "grade"),
    [
        ("ad_sample_insufficient", {"clicks": 10}, "B"),
        ("ad_uncontrolled", {"clicks": 110, "orders": 1}, "C"),
        ("low_margin", {"margin": 8}, "C"),
        ("high_ad_spend_ratio", {"spend": 30}, "B"),
    ],
)
def test_each_enabled_system_risk_caps_grade(code, facts, grade):
    result, display = run(enabled=(code,), **facts)
    assert result["effective_grade"] == grade
    assert display["grade_cap_applied"] is True
    assert any(x["code"] == code for x in result["risk_hits"])


def test_disabled_system_risk_does_not_apply():
    result, display = run(enabled=(), margin=8)
    assert result["effective_grade"] == "S"
    assert display["grade_cap_applied"] is False


def test_strictest_cap_wins():
    result, _ = run(
        enabled=("high_ad_spend_ratio", "low_margin"),
        margin=8,
        spend=30,
    )
    assert result["effective_grade"] == "C"


@pytest.mark.parametrize(
    ("selected", "grade"),
    [
        (["供应链风险"], "B"),
        (["价格风险"], "C"),
        (["ROI低（Pass）"], "Pass"),
        (["侵权风险"], "Pass"),
        (["资金占用率高"], "S"),
    ],
)
def test_manual_risk_decisions(selected, grade):
    result, _ = run(selected=selected)
    assert result["effective_grade"] == grade
    assert result["operator_decision"] is None


def test_missing_enabled_system_evidence_fails_closed():
    rules = default_risk_rules()
    for rule in rules:
        rule["enabled"] = rule["code"] == "ad_uncontrolled"
    with pytest.raises(ValueError, match="NP_RISK_SYSTEM_EVIDENCE_UNVERIFIED"):
        resolve_final_risks(
            coverage={},
            config={"riskConditions": rules},
            rule_version=3,
            base_grade="S",
            manual_selected=["无"],
            cutoff=CUTOFF,
            first_wfs=FIRST,
        )


def test_conflicting_manual_selection_rejected():
    with pytest.raises(ValueError, match="CONFLICTING_MANUAL"):
        run(selected=["ROI低（Pass）", "ROI低（评级上限）"])
