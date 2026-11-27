"""Deterministic, fail-closed performance score (0..10) with raw Decimal precision."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .rules import dec

Z = Decimal("0")
TEN = Decimal("10")
HUNDRED = Decimal("100")


def clamp(n: Decimal) -> Decimal:
    return max(Z, min(TEN, n))


def up(x: Decimal, zero: Decimal, full: Decimal) -> Decimal:
    return clamp((x - zero) * TEN / (full - zero))


def down(x: Decimal, full: Decimal, zero: Decimal) -> Decimal:
    return clamp((zero - x) * TEN / (zero - full))


def weighted(values: list[tuple[Decimal, Decimal]]) -> Decimal:
    return sum((s * w for s, w in values), Z) / HUNDRED


def evaluate(facts: dict[str, Any], config: dict[str, Any], rule_version: int) -> dict:
    p = config["confirmedScoring"]
    w = config["weights"]
    d = {}
    missing = []
    market = facts.get("market_score")
    d["market"] = dec(market) if market is not None and 0 <= dec(market) <= 10 else None
    if d["market"] is None:
        missing.append("市场竞争人工评分")
    if facts.get("zero_sales_verified") is True:
        # Verified 14-day 0 paid orders: all automatic sub-scores are 0.
        # This is an explicit business rule, NOT fabricated ROI or ad ratios.
        d.update({"speed": Z, "ad": Z, "profit": Z, "trust": Z})
        grade = None
        total = None
        if d["market"] is not None:
            total = Z
            grade = next(
                (
                    name
                    for name in ("S", "A", "B", "C", "D")
                    if dec(config["gradeBands"][name][0]) <= Z <= dec(config["gradeBands"][name][1])
                ),
                None,
            )
            if grade is None:
                missing.append("规则分级区间未覆盖零分")
                total = None
        return {
            "rule_version": rule_version,
            "dimensions": {k: str(v) if v is not None else None for k, v in d.items()},
            "total": str(total) if total is not None else None,
            "grade": grade,
            "missing": missing,
            "risk": ["已核实14天零销量"],
            "ad_excluded": False,
            "ad_sample_insufficient": False,
            "observation_state": "scored" if grade else "insufficient_data",
        }
    first = facts.get("first_order_day")
    qty = facts.get("effective_orders_14d")
    elapsed = facts.get("elapsed_days")
    if elapsed is None or qty is None or (first is None and dec(qty) > 0):
        d["speed"] = None
        missing.append("首次WFS可售日/14天有效订单/首单日")
    else:
        sp = p["speed"]
        o = clamp(dec(qty) / dec(sp["targetOrders"]) * TEN)
        f = (
            Z
            if first is None
            else down(dec(first), dec(sp["firstFullDays"]), dec(sp["firstZeroDays"]))
        )
        d["speed"] = weighted([(f, dec(sp["firstWeight"])), (o, dec(sp["ordersWeight"]))])
    ad_status = facts.get("ad_status")
    if ad_status == "not_run":
        d["ad"] = None
    elif ad_status == "active":
        spend, clicks, orders, revenue = (
            facts.get(k) for k in ("ad_spend_usd", "ad_clicks", "ad_orders", "ad_revenue_usd")
        )
        impressions = facts.get("ad_impressions")
        # Real positive impressions + verified zero clicks/attribution/spend:
        # the advertisement delivered, but produced no observed results.
        if (
            impressions is not None
            and dec(impressions) > 0
            and all(x is not None for x in (spend, clicks, orders, revenue))
            and all(dec(x) == 0 for x in (spend, clicks, orders, revenue))
        ):
            d["ad"] = Z
        elif (
            any(x is None for x in (spend, clicks, orders, revenue))
            or dec(clicks) <= 0
            or dec(spend) <= 0
        ):
            d["ad"] = None
            missing.append("广告点击、花费或归因信息")
        elif (
            (dec(orders) > 0 and dec(revenue) <= 0)
            or (dec(orders) == 0 and dec(revenue) > 0)
            or dec(orders) > dec(clicks)
        ):
            d["ad"] = None
            missing.append("广告归因数据不一致")
        else:
            ad = p["ad"]
            a = (
                Z
                if dec(orders) == 0
                else down(
                    dec(spend) / dec(revenue) * HUNDRED, dec(ad["acosFull"]), dec(ad["acosZero"])
                )
            )
            c = down(dec(spend) / dec(clicks), dec(ad["cpcFull"]), dec(ad["cpcZero"]))
            v = up(dec(orders) / dec(clicks) * HUNDRED, dec(ad["cvrZero"]), dec(ad["cvrFull"]))
            d["ad"] = weighted(
                [(a, dec(ad["acosWeight"])), (c, dec(ad["cpcWeight"])), (v, dec(ad["cvrWeight"]))]
            )
    else:
        d["ad"] = None
        missing.append("无法确认广告未投放或数据未同步")
    roi, margin = facts.get("roi"), facts.get("gross_margin_pct")
    if roi is None or margin is None:
        d["profit"] = None
        missing.append("完整的日销ROI/毛利率成本口径")
    else:
        pr = p["profit"]
        d["profit"] = weighted(
            [
                (up(dec(roi), dec(pr["roiZero"]), dec(pr["roiFull"])), dec(pr["roiWeight"])),
                (
                    up(dec(margin), dec(pr["marginZero"]), dec(pr["marginFull"])),
                    dec(pr["marginWeight"]),
                ),
            ]
        )
    units = facts.get("valid_units_14d")
    orders = facts.get("valid_orders_14d")
    ratio = facts.get("trust_order_units_ratio_pct")

    if (
        any(v is None for v in (units, orders, ratio))
        or dec(units) <= 0
        or dec(orders) <= 0
        or dec(orders) > dec(units)
        or dec(ratio) < 0
        or dec(ratio) > HUNDRED
        or abs(dec(ratio) - dec(orders) / dec(units) * HUNDRED) > Decimal("0.000001")
    ):
        d["trust"] = None
        missing.append("MART累计销售件数/订单数/订单件数比")
    else:
        tr = p["trust"]
        d["trust"] = weighted(
            [
                (
                    clamp(dec(units) / dec(tr["targetUnits"]) * TEN),
                    dec(tr["unitsWeight"]),
                ),
                (
                    up(
                        dec(ratio),
                        dec(tr["singleRatioZero"]),
                        dec(tr["singleRatioFull"]),
                    ),
                    dec(tr["singleRatioWeight"]),
                ),
            ]
        )
    no_ads = ad_status == "not_run"
    no_orders = no_ads and qty == 0 and (orders is None or orders == 0)
    continuation = bool(
        no_orders and elapsed is not None and dec(elapsed) >= dec(p["speed"]["observationDays"])
    )
    total = None
    grade = None
    risk = []
    if not missing:
        applicable = [k for k in d if k != "ad" or not no_ads]
        total = clamp(
            sum((d[k] * dec(w[k]) for k in applicable), Z) / sum((dec(w[k]) for k in applicable), Z)
        )
        # Configured grade bands are active business rules, not decorative UI.
        rounded = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        grade = next(
            (
                g
                for g in ("S", "A", "B", "C", "D")
                if dec(config["gradeBands"][g][0]) <= rounded <= dec(config["gradeBands"][g][1])
            ),
            None,
        )
        if grade is None:
            missing.append("规则分级区间未覆盖评分")
            total = None
        # Verified automatic vetoes; other qualitative risks require a separately recorded
        # human finding.
        if (
            grade is not None
            and roi is not None
            and dec(roi) < Decimal(".5")
            and _enabled(config, "ROI 低（Pass）")
        ):
            grade = "Pass"
            risk.append("ROI 低（Pass）")
        if (
            grade is not None
            and roi is not None
            and Decimal(".5") <= dec(roi) < Decimal(".8")
            and _enabled(config, "ROI 低（评级上限）")
        ):
            if grade in ("S", "A"):
                grade = "B"
            risk.append("ROI 低（评级上限）")
        if (
            grade is not None
            and margin is not None
            and dec(margin) < 10
            and _enabled(config, "毛利率过低")
        ):
            grade = "Pass"
            risk.append("毛利率过低")

    def encode(x):
        return None if x is None else str(x)

    return {
        "rule_version": rule_version,
        "dimensions": {k: encode(v) for k, v in d.items()},
        "total": encode(total),
        "grade": grade,
        "missing": missing,
        "risk": risk,
        "ad_excluded": no_ads,
        "ad_sample_insufficient": ad_status == "active"
        and facts.get("ad_clicks") is not None
        and dec(facts["ad_clicks"]) < dec(p["ad"]["minClicks"]),
        "observation_state": "continue_observation"
        if continuation
        else "scored"
        if grade
        else "insufficient_data",
    }


def _enabled(config, name):
    return any(r.get("name") == name and r.get("enabled") for r in config.get("vetoes", []))
