"""Existing new-product rule API can persist the risk configuration payload."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.modules.new_products import rules
from app.modules.new_products.risk_conditions import default_risk_rules


def draft():
    return {
        "weights": dict(rules.DEFAULT_WEIGHTS),
        "confirmedScoring": deepcopy(rules.DEFAULT_PARAMETERS),
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
        "scoreCriteria": {},
        "penalties": [],
        "vetoes": [],
        "riskConditions": default_risk_rules(),
    }


def test_risk_rules_apply_accepts_all_seventeen_without_old_deductions():
    config = draft()
    assert rules.validate("performance", config) is config
    assert len(config["riskConditions"]) == 17


def test_rule_apply_rejects_legacy_penalties_and_vetoes():
    config = draft()
    config["penalties"] = [{"enabled": True, "name": "广告数据不足", "deduct": 1}]
    with pytest.raises(ValueError, match="已取消通用扣分"):
        rules.validate("performance", config)
    config = draft()
    config["vetoes"] = [{"enabled": True, "name": "毛利率过低"}]
    with pytest.raises(ValueError, match="已取消通用扣分"):
        rules.validate("performance", config)


def test_rule_apply_rejects_incomplete_risk_block():
    config = draft()
    config["riskConditions"].pop()
    with pytest.raises(ValueError, match="RISK_CONFIGURATION_MUST_INCLUDE_ALL_17_RULES"):
        rules.validate("performance", config)


def test_rule_apply_rejects_unknown_or_duplicate_risk_rules():
    config = draft()
    config["riskConditions"][1]["code"] = "malicious"
    with pytest.raises(ValueError, match="RISK_RULE_CODE_INVALID_OR_DUPLICATE"):
        rules.validate("performance", config)
    config = draft()
    config["riskConditions"][1]["code"] = config["riskConditions"][0]["code"]
    with pytest.raises(ValueError, match="RISK_RULE_CODE_INVALID_OR_DUPLICATE"):
        rules.validate("performance", config)


def test_default_margin_cap_is_enabled_and_ads_are_opt_in():
    config = draft()
    values = {row["code"]: row for row in config["riskConditions"]}
    assert values["low_margin"]["limit"] == "C"
    assert values["low_margin"]["enabled"] is True
    assert not values["ad_uncontrolled"]["enabled"]


def test_ad_uncontrolled_requires_positive_integer_clicks_and_valid_cvr():
    config = draft()
    row = next(r for r in config["riskConditions"] if r["code"] == "ad_uncontrolled")
    row["enabled"] = True
    row["params"]["min_clicks"] = 0
    with pytest.raises(ValueError, match="RISK_PARAMETER_MUST_BE_POSITIVE"):
        rules.validate("performance", config)
    row["params"]["min_clicks"] = 100
    row["params"]["cvr_below_pct"] = 101
    with pytest.raises(ValueError, match="RISK_PERCENTAGE_INVALID"):
        rules.validate("performance", config)
    row["params"]["cvr_below_pct"] = 2
    assert rules.validate("performance", config) is config


def test_disabled_legacy_spend_rule_is_readable_but_cannot_be_republished_unchanged():
    from app.modules.new_products.risk_conditions import normalize_risk_rules

    config = draft()
    row = next(r for r in config["riskConditions"] if r["code"] == "ad_uncontrolled")
    row["params"] = {"min_spend_usd": None, "max_ad_orders": 0}
    converted = normalize_risk_rules(config["riskConditions"])
    new_rule = next(r for r in converted if r["code"] == "ad_uncontrolled")
    assert new_rule["params"] == {"min_clicks": 100, "cvr_below_pct": 2.0}
    assert new_rule["enabled"] is False
    with pytest.raises(ValueError, match="旧版广告失控规则必须改为点击/CVR阈值"):
        rules.validate("performance", config)
    row["enabled"] = True
    with pytest.raises(ValueError, match="RISK_LEGACY_SPEND_RULE_REQUIRES_RECONFIGURATION"):
        normalize_risk_rules(config["riskConditions"])


def test_legacy_rule_config_can_remain_readable_without_risk_block():
    from app.modules.new_products.risk_conditions import normalize_risk_rules

    assert len(normalize_risk_rules(None)) == 17


def test_cannot_republish_retired_risk_in_new_rule_version():
    config = draft()
    config["riskConditions"].append(
        {
            "code": "ad_sudden_change",
            "name": "广告数据骤变",
            "source": "manual",
            "enabled": True,
            "limit": "none",
            "params": {},
        }
    )
    with pytest.raises(ValueError, match="RISK_RETIRED_RULE_CANNOT_BE_PUBLISHED"):
        rules.validate("performance", config)
