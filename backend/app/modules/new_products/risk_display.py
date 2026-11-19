"""Read-only new-product risk UI projection from verified saved per-identity evidence.

Does not requery source tables, write score/grade, or alter the operator's
assessment. For frozen legacy results without captured risk proof, fail closed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .risk_conditions import assess_risks, normalize_risk_rules

EXPECTED_POLICY = "returns_ignored_samples_excluded_sample_ads_included"


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return value if value.is_finite() else None


def _text(value: Any, decimals: int = 2) -> str:
    number = _number(value)
    if number is None:
        return "—"
    if decimals == 0:
        return f"{number:.0f}"
    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _base(status: str, rule: dict[str, Any], basis: str, cutoff: str | None):
    return {
        "code": rule["code"],
        "name": rule["name"],
        "status": status,
        "enabled": rule["enabled"],
        "limit": rule["limit"],
        "basis": basis,
        "cutoff_la": cutoff,
    }


def _blocked(rules: list[dict[str, Any]], reason: str, rule_version: int) -> dict[str, Any]:
    return {
        "source": "saved_verified_risk_evidence",
        "rule_version": rule_version,
        "rules": [
            _base(
                "disabled" if not r["enabled"] else "unverified",
                r,
                "规则未启用" if not r["enabled"] else reason,
                None,
            )
            for r in rules
            if r["source"] == "system"
        ],
        "grade_cap_applied": False,
    }


def build_saved_risk_display(
    coverage: dict[str, Any] | None,
    configured: list[dict[str, Any]] | None,
    *,
    cutoff_la: date,
    first_wfs: date | str | None,
    rule_version: int,
) -> dict[str, Any]:
    """Pure projection: only verified saved fact blocks matching cutoff may trigger.

    All four rules share the same effective LA business-day cutoff. Missing or
    stale source blocks become 'unverified', never simulated zero or a false hit.
    No cap is written to official grade: grade_cap_applied stays false until
    the formal scoring publisher is explicitly connected in another change.
    """
    try:
        rules = normalize_risk_rules(configured)
    except (ValueError, TypeError, KeyError):
        rules = normalize_risk_rules(None)
        return _blocked(rules, "保存的风险配置无效，无法执行系统识别", rule_version)
    if configured is None:
        return _blocked(rules, "尚未发布配置风险条件，不能按默认规则推断命中", rule_version)
    if not isinstance(coverage, dict):
        return _blocked(rules, "当前商品缺少已保存的风险证据", rule_version)
    final = coverage.get("evaluation_final_snapshot")
    if isinstance(final, dict):
        frozen = final.get("system_risk_display")
        if isinstance(frozen, dict) and isinstance(frozen.get("rules"), list):
            # Only already frozen risk proof can authorize historical display.
            return frozen
        return _blocked(rules, "正式测评已冻结，但历史快照未保存风险证据", rule_version)
    cutoff = cutoff_la.isoformat()
    first_day = first_wfs.isoformat() if isinstance(first_wfs, date) else first_wfs
    if not isinstance(first_day, str) or len(first_day) != 10 or first_day > cutoff:
        return _blocked(rules, "首次 WFS 可售日期未核实", rule_version)
    ads = coverage.get("ad_display_v1")
    profit = coverage.get("new_products_testing_profit_v2")
    facts: dict[str, Any] = {
        "ad_status_cumulative": "unknown",
        "profit_calc_status": "partial",
    }
    ad_reason = "完整累计广告证据未核实"
    profit_reason = "独立累计利润证据未核实"
    ad_ok = False
    profit_ok = False
    if isinstance(ads, dict):
        if ads.get("window_end_la") != cutoff:
            ad_reason = "广告快照截止日不是最近完整洛杉矶业务日"
        elif ads.get("status") != "complete":
            ad_reason = "广告快照状态未完整核实：" + str(ads.get("status") or "missing")
        else:
            source = ads.get("facts")
            if isinstance(source, dict):
                spend = _number(source.get("ad_total_spend_usd"))
                clicks = _number(source.get("ad_total_clicks"))
                orders = _number(source.get("ad_total_orders"))
                first = ads.get("window_start_la")
                if (
                    first == first_day
                    and spend is not None
                    and spend >= 0
                    and clicks is not None
                    and orders is not None
                    and clicks >= 0
                    and orders >= 0
                    and orders <= clicks
                    and clicks == clicks.to_integral_value()
                    and orders == orders.to_integral_value()
                ):
                    ad_ok = True
                    facts.update(
                        {
                            "ad_status_cumulative": (
                                "active" if (spend > 0 or clicks > 0) else "not_run"
                            ),
                            "ad_clicks_cumulative": str(clicks),
                            "ad_orders_cumulative": str(orders),
                        }
                    )
                else:
                    ad_reason = "累计广告首次可售日、点击、花费或订单数据缺失/不一致"
    if isinstance(profit, dict):
        if profit.get("through_la") != cutoff:
            profit_reason = "利润快照截止日不是最近完整洛杉矶业务日"
        elif (
            profit.get("status") != "scored"
            or profit.get("policy") != EXPECTED_POLICY
            or profit.get("missing")
        ):
            profit_reason = "独立利润证据未完成核实"
        else:
            margin = _number(profit.get("gross_margin_pct"))
            revenue = _number(profit.get("sales_amount_usd"))
            spend = _number(profit.get("ad_spend_usd"))
            if (
                margin is not None
                and revenue is not None
                and revenue > 0
                and spend is not None
                and spend >= 0
            ):
                profit_ok = True
                facts.update(
                    {
                        "profit_calc_status": "scored",
                        "gross_margin_pct": str(margin),
                        "sales_amount_usd": str(revenue),
                        "ad_total_spend_usd": str(spend),
                    }
                )
            else:
                profit_reason = "累计利润率、销售额或广告费用缺少可靠证据"
    result = assess_risks(base_grade=None, facts=facts, risk_rules=rules)
    hits = {x["code"]: x for x in result["risk_hits"] if x["source"] == "system"}
    issues = {x["code"]: x["reason"] for x in result["risk_evidence_issues"]}
    output = []
    for r in rules:
        if r["source"] != "system":
            continue
        code = r["code"]
        if not r["enabled"]:
            output.append(_base("disabled", r, "规则未启用", None))
            continue
        if code in {"ad_sample_insufficient", "ad_uncontrolled"} and not ad_ok:
            output.append(_base("unverified", r, ad_reason, None))
            continue
        if code in {"low_margin", "high_ad_spend_ratio"} and not profit_ok:
            output.append(_base("unverified", r, profit_reason, None))
            continue
        if code in issues:
            output.append(_base("unverified", r, str(issues[code]), None))
            continue
        status = "hit" if code in hits else "clear"
        threshold = r["params"]
        if code == "ad_sample_insufficient":
            if facts["ad_status_cumulative"] == "not_run":
                basis = "核实无广告花费，不适用广告点击样本不足条件"
            else:
                basis = (
                    f"累计广告点击 {_text(facts['ad_clicks_cumulative'], 0)} 次；"
                    f"规则：少于 {threshold['clicks_below']} 次"
                )
        elif code == "ad_uncontrolled":
            if facts["ad_status_cumulative"] == "not_run":
                basis = "核实无广告花费，不适用广告失控条件"
            else:
                clicks = _number(facts["ad_clicks_cumulative"])
                orders = _number(facts["ad_orders_cumulative"])
                cvr = (orders / clicks * 100) if clicks else None
                basis = (
                    f"累计广告点击 {_text(clicks, 0)} 次；归因订单 {_text(orders, 0)} 单；"
                    f"CVR {_text(cvr)}%；规则：点击至少 {threshold['min_clicks']} 次"
                    f"且 CVR 低于 {threshold['cvr_below_pct']}%"
                )
        elif code == "low_margin":
            basis = (
                f"累计利润率 {_text(facts['gross_margin_pct'])}%；"
                f"规则：低于 {threshold['margin_below_pct']}%"
            )
        else:
            spend = _number(facts["ad_total_spend_usd"])
            revenue = _number(facts["sales_amount_usd"])
            ratio = spend / revenue * 100 if revenue else None
            basis = (
                f"累计广告费 ${_text(spend)}；累计销售额 ${_text(revenue)}；"
                f"广告占比 {_text(ratio)}%；规则：超过 {threshold['share_above_pct']}%"
            )
        output.append(_base(status, r, basis, cutoff))
    return {
        "source": "saved_verified_risk_evidence",
        "rule_version": rule_version,
        "rules": output,
        "grade_cap_applied": False,
    }
