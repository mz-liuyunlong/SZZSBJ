"""Explain READ-ONLY clearance evaluations without inventing missing facts.

This is presentation evidence, NOT a second clearance decision engine. Existing
business evaluator remains authoritative for high/medium risk. All keys relate to
(source_account_ref, store_id, item_id); SKU is informational only.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    from math import isfinite

    return result if isfinite(result) else None


def val(rules: Any, name: str, default: Any = None) -> Any:
    if isinstance(rules, dict):
        return rules.get(name, default)
    return getattr(rules, name, default)


def evidence_for_snapshot(
    snapshot: dict,
    rules: Any,
    *,
    listing: Any = None,
    first_wfs_date: date | None = None,
    as_of: date | None = None,
) -> dict:
    """Build complete per-rule diagnostics using factual metrics only.

    Every rule has one of hit / not_hit / insufficient / disabled. Ambiguous
    facts never become zero. No writes, SQL or rule admission occur here.
    """
    metrics = snapshot.get("metrics") or {}
    gaps = set(snapshot.get("data_gaps") or [])
    as_of = as_of or date.today()

    def m(key):
        return num(metrics.get(key))

    entries: list[dict] = []

    def add(
        code: str,
        name: str,
        enabled: bool,
        *,
        actual: Any,
        threshold: Any,
        formula: str,
        source: str,
        hit: bool | None,
        severity: str = "low",
        effect: str = "auxiliary",
        context: dict | None = None,
        missing: list[str] | None = None,
    ):
        status = (
            "disabled"
            if not enabled
            else ("insufficient" if hit is None else "hit" if hit else "not_hit")
        )
        evidence = {"source": source, "formula": formula, **(context or {})}
        entries.append(
            {
                "code": code,
                "name": name,
                "enabled": bool(enabled),
                "status": status,
                "severity": severity,
                "effect": effect,
                "actual_value": actual,
                "threshold": threshold,
                "evidence": evidence,
                "missing_fields": missing if status == "insufficient" else [],
                "explanation": (
                    "规则已关闭"
                    if status == "disabled"
                    else "数据不足，未进行该项判定"
                    if status == "insufficient"
                    else "实际值达到已配置条件"
                    if status == "hit"
                    else "已校验，未达到已配置条件"
                ),
            }
        )

    available = m("wfs_available")
    sales30 = m("sales_30d")
    sales14 = m("sales_14d")
    sales7 = m("sales_7d")
    complete30 = metrics.get("complete_30d_window")
    if complete30 is None:
        complete30 = metrics.get("incomplete_30d") is False
    window_days = val(rules, "selloutPeriodDays", val(rules, "sellout_days_period", 30))
    if window_days not in (7, 14, 30):
        window_days = 30
    period_units = m(f"sales_{window_days}d")
    # A Listing aggregate may be displayed without certifying that every
    # expected daily fact exists. Rule evidence requires verified coverage.

    def verified(days: int) -> bool:
        complete = metrics.get(f"complete_{days}d_window")
        if complete is None:
            incomplete = metrics.get(f"incomplete_{days}d")
            complete = (not incomplete) if isinstance(incomplete, bool) else False
        return complete is True

    verified_period = verified(window_days)
    estimated = (
        int(-(-available * window_days // period_units))
        if available is not None and period_units is not None and period_units > 0
        else None
    )
    infinite = period_units == 0 and available is not None and available > 0
    actual_cov = "∞" if infinite else estimated
    coverage_context = {
        "wfs_available": available,
        "period_days": window_days,
        "units_in_period": period_units,
        "daily_average": (period_units / window_days if period_units is not None else None),
        "formula": "WFS可售件数 ÷ (统计周期销量 ÷ 周期天数)，向上取整",
    }
    for code, label, field, severity in [
        ("coverage_high", "预计售罄：高风险", "highCoverage", "high"),
        ("coverage_medium", "预计售罄：中风险", "mediumCoverage", "medium"),
        ("coverage_assist", "预计售罄：经营辅助", "assistCoverage", "low"),
    ]:
        threshold = num(val(rules, field))
        hit = (
            None
            if not verified_period or actual_cov is None or threshold is None
            else True
            if infinite
            else estimated >= threshold
        )
        add(
            code,
            label,
            bool(val(rules, "enableCoverage", True)),
            actual=actual_cov,
            threshold={"operator": ">=", "value": threshold, "unit": "天"},
            formula=coverage_context["formula"],
            source="Listing管理/WFS库存与销量",
            hit=hit,
            severity=severity,
            effect="level" if code != "coverage_assist" else "assisted_only",
            context=coverage_context,
            missing=[
                k
                for k, v in (("wfs_available", available), (f"sales_{window_days}d", period_units))
                if v is None
            ],
        )

    first_days = m("first_wfs_days")
    listed_days = m("listing_days")
    first_stock_iso = first_wfs_date.isoformat() if first_wfs_date else None
    listed_at = getattr(listing, "listing_start_at_utc", None) if listing else None
    listed_at_iso = listed_at.isoformat() if isinstance(listed_at, (date, datetime)) else None
    time_context = {
        "listing_start_at_utc": listed_at_iso,
        "listing_days": listed_days,
        "first_wfs_available_date_la": first_stock_iso,
        "first_wfs_days": first_days,
        "as_of_date_la": as_of.isoformat(),
        "timezone": "America/Los_Angeles (business date); Listing start in UTC",
    }
    zero_days = val(rules, "zeroLookback", 30)
    zero_sales = m(f"sales_{zero_days}d") if zero_days in (7, 14, 30) else None
    zero_min_days = num(val(rules, "minListingDays", val(rules, "newProductProtectionDays", 60)))
    zero_hit = (
        None
        if not verified(zero_days)
        or zero_sales is None
        or first_days is None
        or zero_min_days is None
        else zero_sales == 0 and first_days >= zero_min_days
    )
    add(
        "zero_sales",
        "连续零销量",
        bool(val(rules, "enableZero", True)),
        actual={"units": zero_sales, "observation_days": zero_days, "first_wfs_days": first_days},
        threshold={"units": 0, "first_wfs_days_gte": zero_min_days},
        formula="观察期总销量=0 且首次WFS有货天数达到最低观察期",
        source="每日销售/Listing首次WFS有货日期",
        hit=zero_hit,
        severity="high",
        effect="level",
        context=time_context,
        missing=[
            k for k, v in (("zero_sales", zero_sales), ("first_wfs_days", first_days)) if v is None
        ],
    )

    # Independent profit rules; no double-counting of the same profit abnormality.
    profit7, profit14 = m("profit_7d_usd"), m("profit_14d_usd")
    add(
        "loss_7d_14d",
        "近7天/14天持续亏损",
        bool(val(rules, "enableProfit", True)),
        actual={"profit_7d_usd": profit7, "profit_14d_usd": profit14},
        threshold={"profit_7d_usd": "< 0", "profit_14d_usd": "< 0"},
        formula="7天利润<0 且14天利润<0",
        source="每日销售净利润",
        hit=None
        if not (verified(7) and verified(14)) or profit7 is None or profit14 is None
        else profit7 < 0 and profit14 < 0,
        severity="medium",
        effect="assisted_only",
        missing=[
            k for k, v in (("profit_7d_usd", profit7), ("profit_14d_usd", profit14)) if v is None
        ],
    )
    margin = m("margin_30d_percent")
    margin_threshold = num(val(rules, "margin30Threshold"))
    add(
        "margin_30d",
        "30天利润率偏低",
        bool(val(rules, "enableMargin30", True)),
        actual=margin,
        threshold={"operator": "<", "value": margin_threshold, "unit": "%"},
        formula="30天利润 ÷ 30天销售额 × 100%",
        source="每日销售",
        hit=None
        if not verified(30) or margin is None or margin_threshold is None
        else margin < margin_threshold,
        severity="low",
        effect="assisted_only",
        missing=["margin_30d_percent"] if margin is None else [],
    )

    prev7 = sales14 - sales7 if sales14 is not None and sales7 is not None else None
    drop = (
        100 * (prev7 - sales7) / prev7
        if prev7 is not None and sales7 is not None and prev7 > 0
        else None
    )
    drop_threshold = num(val(rules, "salesDropPercent"))
    base_min = num(val(rules, "minBaseSales", val(rules, "minSalesDropBase", 10)))
    decrease_min = num(val(rules, "minSalesDropUnits", 5))
    drop_hit = (
        None
        if not (verified(7) and verified(14)) or drop is None or drop_threshold is None
        else prev7 >= (base_min or 0)
        and prev7 - sales7 >= (decrease_min or 0)
        and drop >= drop_threshold
    )
    add(
        "sales_decline",
        "近期销量下滑",
        bool(val(rules, "enableDecline", True)),
        actual={"recent_7d": sales7, "previous_7d": prev7, "decline_percent": drop},
        threshold={
            "decline_percent_gte": drop_threshold,
            "minimum_previous_units": base_min,
            "minimum_decrease_units": decrease_min,
        },
        formula="(前7天销量－近7天销量) ÷ 前7天销量 ×100%",
        source="每日销售/Listing",
        hit=drop_hit,
        effect="assisted_only",
        missing=[] if drop is not None else ["previous_7d_or_recent_7d_sales"],
    )

    ad7, ad30 = m("ad_ratio_7d_percent"), m("ad_ratio_30d_percent")
    ad_diff = ad7 - ad30 if ad7 is not None and ad30 is not None else None
    ad_limit = num(val(rules, "adRateIncrease"))
    add(
        "ad_ratio_rising",
        "广告占比持续升高",
        bool(val(rules, "enableAd", True)),
        actual={
            "ad_ratio_7d": ad7,
            "ad_ratio_30d": ad30,
            "difference_percentage_points": ad_diff,
            "profit_7d_usd": profit7,
        },
        threshold={"increase_points_gte": ad_limit, "profit_7d_usd": "< 0"},
        formula="近7天广告占比－30天广告占比，且近7天利润亏损",
        source="每日销售/广告费",
        hit=(
            None
            if ad_diff is None or profit7 is None or ad_limit is None
            else ad_diff >= ad_limit and profit7 < 0
        ),
        effect="assisted_only",
    )

    returns, rating, reviews = m("returns_30d"), m("rating"), m("review_count")
    return_rate = m("return_rate_30d_percent")
    if return_rate is None and returns is not None and sales30 is not None and sales30 > 0:
        return_rate = returns / sales30 * 100
    rt = num(val(rules, "returnRate"))
    add(
        "returns_30d",
        "30天退货率偏高",
        bool(val(rules, "enableReturns", True)),
        actual={"return_qty": returns, "units_sold": sales30, "return_rate_percent": return_rate},
        threshold={
            "return_rate_gte": rt,
            "minimum_returns": num(val(rules, "minReturnCount", 5)),
            "minimum_sales": num(val(rules, "minReturnSales", 30)),
        },
        formula="30天退货件数 ÷ 30天销售件数 ×100%",
        source="退货管理/每日销售",
        hit=None
        if not verified(30) or return_rate is None or rt is None
        else (
            return_rate >= rt
            and (returns or 0) >= num(val(rules, "minReturnCount", 5))
            and (sales30 or 0) >= num(val(rules, "minReturnSales", 30))
        ),
        effect="assisted_only",
    )
    rating_lim = num(val(rules, "ratingThreshold"))
    add(
        "rating_low",
        "商品评分偏低",
        bool(val(rules, "enableRating", True)),
        actual={"rating": rating, "review_count": reviews},
        threshold={
            "rating_lt": rating_lim,
            "min_reviews": num(val(rules, "minRatingReviewCount", 10)),
        },
        formula="评分小于阈值且评论数达到最低样本量",
        source="Listing管理",
        hit=None
        if rating is None or reviews is None or rating_lim is None
        else (rating < rating_lim and reviews >= num(val(rules, "minRatingReviewCount", 10))),
        effect="assisted_only",
    )

    capital = m("capital_at_cost_usd")
    cap = num(val(rules, "minStockCapital"))
    add(
        "inventory_capital",
        "库存资金占用",
        bool(val(rules, "enableCapitalPriority", True)),
        actual=capital,
        threshold={"operator": ">=", "value": cap, "unit": "USD"},
        formula="WFS可售库存 × 单件库存成本（以当前生效财务口径为准）",
        source="产品管理/仓储费与店铺佣金配置",
        hit=None if capital is None or cap is None else capital >= cap,
        effect="priority_only",
    )

    inbound = num(getattr(listing, "inbound_quantity", None)) if listing else None
    inbound_threshold = num(val(rules, "inboundConflictMin"))
    add(
        "inbound_conflict",
        "在途补货与积压冲突",
        bool(val(rules, "enableInboundConflict", True)),
        actual={"inbound_units": inbound, "sellout_days": actual_cov},
        threshold={
            "inbound_units_gte": inbound_threshold,
            "coverage_days_gte": num(val(rules, "assistCoverage")),
        },
        formula="在途补货件数达到阈值且库存覆盖天数达到辅助阈值",
        source="Listing管理/采购在途",
        hit=(
            None
            if inbound is None or actual_cov is None or inbound_threshold is None
            else inbound >= inbound_threshold
            and (infinite or estimated >= num(val(rules, "assistCoverage", 0)))
        ),
        effect="priority_only",
    )

    protection_days = num(val(rules, "newProductProtectionDays", val(rules, "minListingDays", 60)))
    add(
        "new_product_protection",
        "新品保护",
        bool(val(rules, "enableNewProductProtection", True)),
        actual={"first_wfs_days": first_days, "listing_days": listed_days},
        threshold={"protected_days_lte": protection_days},
        formula="WFS首次有库存日期至计算日的天数与新品保护期比较",
        source="Listing首次有货日期",
        hit=None
        if first_days is None or protection_days is None
        else first_days <= protection_days,
        severity="low",
        effect="protection_only",
        context=time_context,
        missing=["first_wfs_available_date_la"] if first_days is None else [],
    )

    # Remaining confirmed auxiliary, protection and urgency rules. Absent
    # sources are marked insufficient (never false/zero) and never auto-apply.
    last_sale_days = m("last_sale_days")
    last_sale_limit = num(val(rules, "lastSaleDaysLimit"))
    add(
        "last_sale_gap",
        "距离最近一次出单过久",
        bool(val(rules, "enableLastSale", False)),
        actual={"last_sale_days": last_sale_days, "sellout_days": actual_cov},
        threshold={
            "last_sale_days_gte": last_sale_limit,
            "coverage_days_gte": num(val(rules, "assistCoverage")),
        },
        formula="最近一次出单距今天数达到阈值且库存覆盖天数达到辅助条件",
        source="每日销售/Listing管理",
        hit=(
            None
            if last_sale_days is None or last_sale_limit is None or actual_cov is None
            else last_sale_days >= last_sale_limit
            and (infinite or estimated >= num(val(rules, "assistCoverage", 0)))
        ),
        effect="assisted_only",
    )
    active_days = m("active_sales_days_30d")
    active_limit = num(val(rules, "maxActiveSalesDays30"))
    add(
        "rare_sales_days",
        "30天内出单天数偏少",
        bool(val(rules, "enableActiveDays", False)),
        actual=active_days,
        threshold={"operator": "<=", "value": active_limit, "unit": "天"},
        formula="最近30天至少售出1件的自然日数量",
        source="每日销售",
        hit=None if active_days is None or active_limit is None else active_days <= active_limit,
        effect="assisted_only",
    )
    clicks, orders = m("ad_clicks_30d"), m("ad_orders_30d")
    conversion = (
        orders / clicks * 100 if clicks is not None and clicks > 0 and orders is not None else None
    )
    conversion_limit = num(val(rules, "maxAdConversionPercent"))
    clicks_min = num(val(rules, "minAdClicks30"))
    add(
        "ad_low_conversion",
        "广告点击充分但转化低",
        bool(val(rules, "enableAdConversion", False)),
        actual={"clicks": clicks, "orders": orders, "conversion_percent": conversion},
        threshold={"min_clicks": clicks_min, "conversion_lt": conversion_limit},
        formula="30天广告归因订单÷广告点击×100%，同时达到最低点击数",
        source="广告搜索词/广告归因",
        hit=None
        if conversion is None or clicks_min is None or conversion_limit is None
        else clicks >= clicks_min and conversion < conversion_limit,
        effect="assisted_only",
    )
    net_units = m("net_units_30d")
    net_max = num(val(rules, "maxNetUnits30"))
    add(
        "net_sales_low",
        "30天净销量偏低",
        bool(val(rules, "enableNetSales", False)),
        actual=net_units,
        threshold={"operator": "<=", "value": net_max, "unit": "件"},
        formula="同口径净销量（实际销售件数扣除确认退货件数）",
        source="每日销售/退货管理",
        hit=None if net_units is None or net_max is None else net_units <= net_max,
        effect="assisted_only",
    )
    before7 = sales14 - sales7 if sales14 is not None and sales7 is not None else None
    recovery = (
        (sales7 / before7 - 1) * 100
        if before7 is not None and before7 > 0 and sales7 is not None
        else None
    )
    recovery_min = num(val(rules, "minSalesForRecovery"))
    recovery_pct = num(val(rules, "salesRecoveryPercent"))
    add(
        "sales_recovery_protection",
        "近期销量恢复保护",
        bool(val(rules, "enableRecoveryProtection", False)),
        actual={
            "previous_7d_units": before7,
            "recent_7d_units": sales7,
            "increase_percent": recovery,
        },
        threshold={"minimum_7d_units": recovery_min, "increase_percent_gte": recovery_pct},
        formula="(近7天销量÷前7天销量−1)×100%，双方均满足最低销量",
        source="每日销售",
        hit=None
        if recovery is None
        or recovery_min is None
        or recovery_pct is None
        or not (verified(7) and verified(14))
        else (before7 >= recovery_min and sales7 >= recovery_min and recovery >= recovery_pct),
        effect="protection_only",
    )
    buy_box = getattr(listing, "has_buy_box", None) if listing else None
    add(
        "buybox_protection",
        "购物车异常保护",
        bool(val(rules, "enableBuyBoxProtection", False)),
        actual=buy_box,
        threshold={"buy_box": False},
        formula="存在BuyBox异常时暂缓普通经营风险升级",
        source="Listing当前BuyBox状态",
        hit=None if buy_box is None else buy_box is False,
        effect="protection_only",
    )
    purchase_pending = m("open_purchase_qty")
    purchase_min = num(val(rules, "purchaseConflictMin"))
    add(
        "purchase_conflict",
        "未完成采购与库存冲突",
        bool(val(rules, "enablePurchaseConflict", False)),
        actual=purchase_pending,
        threshold={"operator": ">=", "value": purchase_min, "unit": "件"},
        formula="尚未关闭的采购在途数量达到配置值",
        source="采购单",
        hit=None
        if purchase_pending is None or purchase_min is None
        else purchase_pending >= purchase_min,
        effect="priority_only",
    )
    risk_days = m("risk_consecutive_days")
    risk_min = num(val(rules, "riskDaysThreshold"))
    add(
        "risk_duration",
        "风险持续时间偏长",
        bool(val(rules, "enableRiskDuration", False)),
        actual=risk_days,
        threshold={"operator": ">=", "value": risk_min, "unit": "天"},
        formula="连续风险快照的风险持续天数",
        source="清货历史风险快照",
        hit=None if risk_days is None or risk_min is None else risk_days >= risk_min,
        effect="priority_only",
    )
    holding = m("estimated_holding_cost30_usd")
    holding_min = num(val(rules, "holdingCost30Threshold"))
    add(
        "holding_cost_30d",
        "预计未来30天持有费偏高",
        bool(val(rules, "enableHoldingCost", False)),
        actual=holding,
        threshold={"operator": ">=", "value": holding_min, "unit": "USD"},
        formula="未来30天实际费率×可售库存，不以历史采购费代替",
        source="WFS仓储成本",
        hit=None if holding is None or holding_min is None else holding >= holding_min,
        effect="priority_only",
    )

    # Preserve any evaluator-generated signals not accounted for above, without
    # guessing their thresholds or claiming they participated in final level.
    for i, signal in enumerate(snapshot.get("signals") or []):
        label = signal.get("name") if isinstance(signal, dict) else str(signal)
        if not label:
            continue
        add(
            f"evaluator_signal_{i}",
            label,
            True,
            actual=signal if isinstance(signal, dict) else None,
            threshold=None,
            formula="待从原规则引擎提取详细计算参数",
            source="清货风险计算器",
            hit=None,
            effect="auxiliary",
            missing=["rule_specific_evidence"],
        )

    # Explicitly excluded permanently: aged stock ratio, age lots, average WFS
    # inventory age and near-fee batch rules, due to missing batch evidence.
    prohibited = {"aged_lot", "aged_ratio", "average_age", "near_storage_fee"}
    assert not any(item["code"] in prohibited for item in entries)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    entries.sort(
        key=lambda d: (d["status"] != "hit", severity_order.get(d["severity"], 3), d["code"])
    )
    proven = snapshot.get("risk") or "unknown"
    if proven in ("unknown", "unreviewed"):
        level = "unknown"
    elif proven in ("high", "medium"):
        level = proven
    else:
        positive = [
            x for x in entries if x["status"] == "hit" and x["effect"] in ("level", "assisted_only")
        ]
        insufficient = [
            x
            for x in entries
            if x["status"] == "insufficient" and x["effect"] in ("level", "assisted_only")
        ]
        level = "low" if positive else "unknown" if insufficient else "none"
    return {
        "risk": level,
        "rule_hits": entries,
        "evaluated_at": datetime.now().astimezone().isoformat(),
        "as_of_date_la": as_of.isoformat(),
        "time_evidence": time_context,
        "rule_version": snapshot.get("rule_version", 0),
        "data_gaps": sorted(gaps),
        "evaluator_reasons": list(snapshot.get("reasons") or []),
    }
