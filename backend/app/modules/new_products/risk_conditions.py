"""Pure, fail-closed risk configuration and recommendation rules for new products.

This module is intentionally side-effect free. It does NOT read or write the DB,
replace the five-dimensional scoring formula, decide the operator's pass/fail,
or enroll itself in the existing V2 publisher. Application-level integration
must be atomic with the rule editor, saved proof, and manual decision flow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

ORDER = ("S", "A", "B", "C", "D")
RANK = {grade: index for index, grade in enumerate(ORDER)}
CAPS = frozenset({"none", "B", "C", "D", "recommend_not_pass"})
SYSTEM = "system"
MANUAL = "manual"

# Numeric defaults not expressly confirmed by the owner stay DISABLED.
# The only enabled system risk is the confirmed low-margin, maximum-C policy.
_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "code": "ad_sample_insufficient",
        "name": "广告数据不足",
        "source": SYSTEM,
        "enabled": False,
        "limit": "B",
        "params": {"clicks_below": 20},
    },
    {
        "code": "ad_uncontrolled",
        "name": "广告失控",
        "source": SYSTEM,
        "enabled": False,
        "limit": "C",
        "params": {"min_clicks": 100, "cvr_below_pct": 2},
    },
    {
        "code": "low_margin",
        "name": "毛利率过低",
        "source": SYSTEM,
        "enabled": True,
        "limit": "C",
        "params": {"margin_below_pct": 10},
    },
    {
        "code": "high_ad_spend_ratio",
        "name": "广告占比过高",
        "source": SYSTEM,
        "enabled": False,
        "limit": "B",
        "params": {"share_above_pct": 25},
    },
    {
        "code": "funding",
        "name": "资金占用率高",
        "source": MANUAL,
        "enabled": True,
        "limit": "none",
        "params": {},
    },
    {
        "code": "seasonal_normal",
        "name": "季节性（一般）",
        "source": MANUAL,
        "enabled": True,
        "limit": "none",
        "params": {},
    },
    {
        "code": "low_price_dependency",
        "name": "低价依赖",
        "source": MANUAL,
        "enabled": True,
        "limit": "none",
        "params": {},
    },
    {
        "code": "roi_very_low",
        "name": "ROI低（Pass）",
        "source": MANUAL,
        "enabled": True,
        "limit": "recommend_not_pass",
        "params": {},
    },
    {
        "code": "roi_low",
        "name": "ROI低（评级上限）",
        "source": MANUAL,
        "enabled": True,
        "limit": "B",
        "params": {},
    },
    {
        "code": "seasonal_severe",
        "name": "季节性（强）",
        "source": MANUAL,
        "enabled": True,
        "limit": "recommend_not_pass",
        "params": {},
    },
    {
        "code": "ip_risk",
        "name": "侵权风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "recommend_not_pass",
        "params": {},
    },
    {
        "code": "compliance_risk",
        "name": "合规风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "recommend_not_pass",
        "params": {},
    },
    {
        "code": "supply_risk",
        "name": "供应链风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "B",
        "params": {},
    },
    {
        "code": "quality_risk",
        "name": "质量风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "recommend_not_pass",
        "params": {},
    },
    {
        "code": "price_risk",
        "name": "价格风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "C",
        "params": {},
    },
    {
        "code": "return_risk",
        "name": "退货风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "B",
        "params": {},
    },
    {
        "code": "platform_risk",
        "name": "平台风险",
        "source": MANUAL,
        "enabled": True,
        "limit": "C",
        "params": {},
    },
)
_BY_CODE = {item["code"]: item for item in _DEFINITIONS}
_NAME_TO_CODE = {item["name"]: item["code"] for item in _DEFINITIONS}


def default_risk_rules() -> list[dict[str, Any]]:
    """Seventeen rules; the manual '无' selection is NOT a configured rule."""
    return [deepcopy(item) for item in _DEFINITIONS]


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return result if result.is_finite() else None


def _validate_params(code: str, params: Mapping[str, Any]) -> dict[str, Any]:
    expected = _BY_CODE[code]["params"]
    if set(params) != set(expected):
        raise ValueError(f"RISK_PARAMETER_FIELDS_INVALID:{code}")
    out = dict(params)
    for field, value in params.items():
        if value is None:
            raise ValueError(f"RISK_PARAMETER_MISSING:{code}:{field}")
        number = _decimal(value)
        if number is None or number < 0:
            raise ValueError(f"RISK_PARAMETER_INVALID:{code}:{field}")
        if field in {"clicks_below", "min_clicks"} and number != number.to_integral_value():
            raise ValueError(f"RISK_PARAMETER_MUST_BE_INTEGER:{code}:{field}")
        if field in {"margin_below_pct", "share_above_pct", "cvr_below_pct"} and number > 100:
            raise ValueError(f"RISK_PERCENTAGE_INVALID:{code}:{field}")
        if field == "min_clicks" and number < 1:
            raise ValueError("RISK_PARAMETER_MUST_BE_POSITIVE:ad_uncontrolled:min_clicks")
        out[field] = int(number) if field in {"clicks_below", "min_clicks"} else float(number)
    return out


def normalize_risk_rules(overrides: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize a complete versioned rule array; legacy absence gets defaults.

    Code/source/name are immutable identities. Only enabled, limit and numeric
    params are editable. Fail closed on duplicates, omissions, and unknown keys.
    """
    if overrides is None:
        return default_risk_rules()
    if not isinstance(overrides, list):
        raise ValueError("RISK_CONFIGURATION_MUST_INCLUDE_ALL_17_RULES")
    if len(overrides) == len(_DEFINITIONS) + 1:
        retired = [
            r for r in overrides if isinstance(r, dict) and r.get("code") == "ad_sudden_change"
        ]
        if len(retired) != 1:
            raise ValueError("RISK_RETIRED_LEGACY_RULE_INVALID")
        old = retired[0]
        if (
            set(old) != {"code", "name", "source", "enabled", "limit", "params"}
            or old["name"] != "广告数据骤变"
            or old["source"] != MANUAL
            or type(old["enabled"]) is not bool
            or old["limit"] not in CAPS
            or old["params"] != {}
        ):
            raise ValueError("RISK_RETIRED_LEGACY_RULE_INVALID")
        overrides = [r for r in overrides if r is not old]
    if len(overrides) != len(_DEFINITIONS):
        raise ValueError("RISK_CONFIGURATION_MUST_INCLUDE_ALL_17_RULES")
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in overrides:
        if not isinstance(item, dict) or set(item) != {
            "code",
            "name",
            "source",
            "enabled",
            "limit",
            "params",
        }:
            raise ValueError("RISK_RULE_STRUCTURE_INVALID")
        code = item["code"]
        if not isinstance(code, str) or code not in _BY_CODE or code in seen:
            raise ValueError("RISK_RULE_CODE_INVALID_OR_DUPLICATE")
        original = _BY_CODE[code]
        if item["name"] != original["name"] or item["source"] != original["source"]:
            raise ValueError(f"RISK_RULE_IDENTITY_CHANGED:{code}")
        if type(item["enabled"]) is not bool:
            raise ValueError(f"RISK_ENABLE_INVALID:{code}")
        if item["limit"] not in CAPS:
            raise ValueError(f"RISK_LIMIT_INVALID:{code}")
        if original["source"] == SYSTEM and item["limit"] in {"none", "recommend_not_pass"}:
            raise ValueError(f"RISK_SYSTEM_LIMIT_MUST_BE_GRADE:{code}")
        params = item["params"]
        if not isinstance(params, dict):
            raise ValueError(f"RISK_PARAMETERS_INVALID:{code}")
        # Already-saved Stage 2 rules may contain the obsolete spend/order
        # predicate. Disabled legacy rules can be safely upgraded on read;
        # enabled ones must be explicitly reconfigured rather than silently
        # changing their meaning.
        if code == "ad_uncontrolled" and set(params) == {"min_spend_usd", "max_ad_orders"}:
            if item["enabled"]:
                raise ValueError("RISK_LEGACY_SPEND_RULE_REQUIRES_RECONFIGURATION")
            params = dict(original["params"])
        output.append(
            {
                **original,
                "enabled": item["enabled"],
                "limit": item["limit"],
                "params": _validate_params(code, params),
            }
        )
        seen.add(code)
    if seen != set(_BY_CODE):
        raise ValueError("RISK_CONFIGURATION_INCOMPLETE")
    return sorted(output, key=lambda item: list(_BY_CODE).index(item["code"]))


def _system_hit(code: str, facts: Mapping[str, Any], params: Mapping[str, Any]):
    """Return (hit, observed, issue); unavailable evidence never counts as a hit."""
    if code == "ad_sample_insufficient":
        status = facts.get("ad_status_cumulative")
        if status == "not_run":
            return False, None, None
        if status != "active":
            return False, None, "广告投放状态未核实"
        clicks = _decimal(facts.get("ad_clicks_cumulative"))
        if clicks is None or clicks < 0:
            return False, None, "广告点击证据缺失"
        return clicks < _decimal(params["clicks_below"]), str(clicks), None
    if code == "ad_uncontrolled":
        status = facts.get("ad_status_cumulative")
        if status == "not_run":
            return False, None, None
        if status != "active":
            return False, None, "广告投放状态未核实"
        clicks = _decimal(facts.get("ad_clicks_cumulative"))
        orders = _decimal(facts.get("ad_orders_cumulative"))
        if (
            clicks is None
            or orders is None
            or clicks < 0
            or orders < 0
            or clicks != clicks.to_integral_value()
            or orders != orders.to_integral_value()
            or orders > clicks
            or clicks == 0
        ):
            return False, None, "完整广告点击或归因订单证据缺失/不一致"
        cvr = orders / clicks * 100
        hit = clicks >= _decimal(params["min_clicks"]) and cvr < _decimal(params["cvr_below_pct"])
        return hit, {"clicks": str(clicks), "orders": str(orders), "cvr_pct": str(cvr)}, None
    if code == "low_margin":
        # Explicit independently calculated full-history normal-sales profit.
        if facts.get("profit_calc_status") != "scored":
            return False, None, "完整利润证据未核实"
        margin = _decimal(facts.get("gross_margin_pct"))
        if margin is None:
            return False, None, "毛利率缺失"
        return margin < _decimal(params["margin_below_pct"]), str(margin), None
    if code == "high_ad_spend_ratio":
        if facts.get("profit_calc_status") != "scored":
            return False, None, "完整利润证据未核实"
        spend = _decimal(facts.get("ad_total_spend_usd"))
        revenue = _decimal(facts.get("sales_amount_usd"))
        if spend is None or revenue is None or spend < 0 or revenue <= 0:
            return False, None, "完整广告总花费或有效销售额证据不足"
        share = spend / revenue * 100
        return share > _decimal(params["share_above_pct"]), str(share), None
    raise ValueError("RISK_UNKNOWN_SYSTEM_RULE")


def assess_risks(
    *,
    base_grade: str | None,
    facts: Mapping[str, Any],
    manual_selected: Sequence[str] = (),
    risk_rules: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return grade suggestion without changing a score or operator decision."""
    rules = normalize_risk_rules(risk_rules)
    if base_grade is not None and base_grade not in RANK:
        raise ValueError("RISK_UNKNOWN_BASE_GRADE")
    selected = list(manual_selected)
    if len(selected) != len(set(selected)) or ("无" in selected and len(selected) > 1):
        raise ValueError("RISK_MANUAL_SELECTION_INVALID")
    invalid = [x for x in selected if x != "无" and x not in _NAME_TO_CODE]
    if invalid:
        raise ValueError("RISK_MANUAL_SELECTION_UNKNOWN")
    enabled_rules = {item["code"]: item for item in rules if item["enabled"]}
    triggered: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    suggested = base_grade
    recommend_not_pass = False
    for rule in rules:
        if not rule["enabled"] or rule["source"] != SYSTEM:
            continue
        hit, observed, issue = _system_hit(rule["code"], facts, rule["params"])
        if issue:
            issues.append({"code": rule["code"], "reason": issue})
        if hit:
            triggered.append(
                {
                    "code": rule["code"],
                    "name": rule["name"],
                    "source": SYSTEM,
                    "limit": rule["limit"],
                    "observed": observed,
                }
            )
    for name in selected:
        if name == "无":
            continue
        code = _NAME_TO_CODE[name]
        rule = enabled_rules.get(code)
        if rule is None or rule["source"] != MANUAL:
            raise ValueError("RISK_MANUAL_RULE_NOT_ENABLED:" + code)
        triggered.append(
            {
                "code": code,
                "name": rule["name"],
                "source": MANUAL,
                "limit": rule["limit"],
                "observed": None,
            }
        )
    for item in triggered:
        limit = item["limit"]
        if limit == "recommend_not_pass":
            recommend_not_pass = True
        elif suggested is not None and limit in RANK and RANK[suggested] < RANK[limit]:
            suggested = limit
    return {
        "base_grade": base_grade,
        "suggested_grade": suggested,
        "risk_hits": triggered,
        "risk_evidence_issues": issues,
        "recommend_not_pass": recommend_not_pass,
        "operator_decision": None,  # Separate human workflow, never inferred.
    }
