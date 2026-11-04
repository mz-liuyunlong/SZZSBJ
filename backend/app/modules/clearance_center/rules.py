"""Deterministic V1 clearance rules. Never infer zero from missing evidence."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any

RULE_VERSION = "clearance-v1-20261104"
METHODS = frozenset({"降价", "促销", "广告清货", "WFS 移除", "弃置"})
DEFAULT_RULES: dict[str, Any] = {
    "high_coverage_days": 180,
    "medium_coverage_days": 90,
    "assisted_coverage_days": 60,
    "zero_sales_days": 30,
    "min_stock_positive_days": 21,
    "min_listing_days": 30,
    "sales_drop_percent": 40,
    "sales_previous_min_units": 10,
    "sales_absolute_drop_min_units": 5,
    "ad_ratio_growth_points": 5,
    "refund_rate_percent": 8,
    "refund_min_sales_units": 30,
    "refund_min_return_units": 5,
    "margin_below_percent": 8,
    "rating_below": 3.8,
    "rating_min_reviews": 10,
    "sales_recovery_percent": 50,
    "recovery_min_units_each_week": 5,
    "new_listing_protection_days": 30,
    "high_stock_capital_usd": 3000,
    "holding_days": 60,
    "safety_stock_units": 0,
    "inventory_max_age_hours": 72,
    "enable_margin_signal": True,
    "enable_refund_signal": True,
    "enable_rating_signal": True,
    "enable_new_listing_protection": True,
    "enable_recovery_protection": True,
}


NUMERIC_THRESHOLD_KEYS = frozenset(
    {
        "sales_drop_percent",
        "ad_ratio_growth_points",
        "refund_rate_percent",
        "margin_below_percent",
        "rating_below",
        "sales_recovery_percent",
        "high_stock_capital_usd",
    }
)


def validate_rules(changes: dict[str, Any]) -> dict[str, Any]:
    if any(key not in DEFAULT_RULES for key in changes):
        raise ValueError("Unknown clearance rule")
    merged = {**DEFAULT_RULES, **changes}
    for key, original in DEFAULT_RULES.items():
        value = merged[key]
        if isinstance(original, bool):
            valid = type(value) is bool
        elif key in NUMERIC_THRESHOLD_KEYS:
            valid = type(value) in (int, float) and number(value) is not None
        else:
            valid = type(value) is int
        if not valid:
            raise ValueError(f"Invalid clearance rule: {key}")
        if type(value) in (int, float) and (value < 0 or value > 3650):
            raise ValueError(f"Clearance rule out of bounds: {key}")
    # Evidence queries are 30-day lookbacks and 72-hour freshness checks.
    # Do not accept silently ignored settings until the matching queries are dynamic.
    if merged["zero_sales_days"] != 30 or merged["inventory_max_age_hours"] != 72:
        raise ValueError("Fixed evidence windows cannot be overridden in V1")
    if not (
        0
        < merged["assisted_coverage_days"]
        < merged["medium_coverage_days"]
        < merged["high_coverage_days"]
    ):
        raise ValueError("Coverage thresholds must increase")
    if merged["min_stock_positive_days"] > merged["zero_sales_days"]:
        raise ValueError("Positive-stock days exceed lookback")
    if merged["safety_stock_units"] < 0 or merged["holding_days"] < 1:
        raise ValueError("Invalid clearance quantity rule")
    return merged


def number(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        x = Decimal(str(v))
        return x if x.is_finite() else None
    except (ValueError, ArithmeticError):
        return None


def money(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _ceil(v: Decimal) -> int:
    return int(v.to_integral_value(rounding=ROUND_CEILING))


def evaluate(
    listing: dict[str, Any], metrics: dict[str, Any], rules: dict[str, Any], *, as_of: date
) -> dict[str, Any]:
    """Return explicit risk, evidence, unknowns and safe quantity suggestion."""
    avail = number(listing.get("wfs_available_quantity"))
    sales30 = number(metrics.get("sales30"))
    sales7 = number(metrics.get("sales7"))
    prev7 = number(metrics.get("prev7"))
    revenue30 = number(metrics.get("revenue30"))
    profit30 = number(metrics.get("profit30"))
    profit7 = number(metrics.get("profit7"))
    profit_prev7 = number(metrics.get("profit_prev7"))
    ad7 = number(metrics.get("ad7"))
    ad_prev7 = number(metrics.get("ad_prev7"))
    revenue7 = number(metrics.get("revenue7"))
    revenue_prev7 = number(metrics.get("revenue_prev7"))
    refund_qty = number(metrics.get("refund_qty"))
    coverage: int | None = None
    reasons: list[str] = []
    warnings: list[str] = []
    signals: dict[str, list[str]] = {}
    cost_complete = bool(metrics.get("cost_complete"))
    sales_complete = bool(metrics.get("sales_complete"))
    inventory_fresh = bool(metrics.get("inventory_fresh"))
    listing_days = metrics.get("listing_days")

    def signal(group: str, reason: str) -> None:
        signals.setdefault(group, []).append(reason)

    if avail is None or avail <= 0 or not inventory_fresh:
        warnings.append("WFS_STOCK_UNAVAILABLE_OR_STALE")
    if sales30 is None or not sales_complete:
        warnings.append("SALES_WINDOW_UNVERIFIED")
    if not cost_complete:
        warnings.append("PROFIT_COST_INCOMPLETE")
    if listing_days is None:
        warnings.append("LISTING_START_UNKNOWN")

    if sales30 is not None and sales30 > 0 and avail is not None and avail > 0 and sales_complete:
        coverage = _ceil(avail * Decimal(30) / sales30)
    if sales7 is not None and prev7 is not None and prev7 >= rules["sales_previous_min_units"]:
        drop = prev7 - sales7
        if (
            drop >= rules["sales_absolute_drop_min_units"]
            and drop * 100 >= prev7 * rules["sales_drop_percent"]
        ):
            signal("SALES", "SALES_DECLINING")
    if cost_complete:
        if (
            profit30 is not None
            and revenue30 is not None
            and revenue30 > 0
            and rules["enable_margin_signal"]
        ):
            if profit30 * 100 < revenue30 * Decimal(str(rules["margin_below_percent"])):
                signal("PROFIT", "LOW_MARGIN_30D")
        if profit7 is not None and profit_prev7 is not None and profit7 < 0 and profit_prev7 < 0:
            signal("PROFIT", "CONSECUTIVE_WEEK_LOSS")
    if (
        ad7 is not None
        and ad_prev7 is not None
        and revenue7 is not None
        and revenue_prev7 is not None
        and revenue7 > 0
        and revenue_prev7 > 0
        and profit7 is not None
        and cost_complete
        and profit7 < 0
    ):
        change_points = (ad7 / revenue7 - ad_prev7 / revenue_prev7) * 100
        if change_points >= Decimal(str(rules["ad_ratio_growth_points"])):
            signal("ADS", "AD_SHARE_INCREASE_AND_LOSS")
    if (
        rules["enable_refund_signal"]
        and refund_qty is not None
        and sales30 is not None
        and sales_complete
        and sales30 >= rules["refund_min_sales_units"]
        and refund_qty >= rules["refund_min_return_units"]
        and refund_qty * 100 >= sales30 * Decimal(str(rules["refund_rate_percent"]))
    ):
        signal("AFTER_SALES", "HIGH_PERIOD_REFUND_RATE")
    rating = number(listing.get("average_rating"))
    reviews = listing.get("review_count")
    if (
        rules["enable_rating_signal"]
        and rating is not None
        and reviews is not None
        and rating > 0
        and rating < Decimal(str(rules["rating_below"]))
        and reviews >= rules["rating_min_reviews"]
    ):
        signal("LISTING_QUALITY", "LOW_LISTING_RATING")

    risk = "low"
    high = False
    if coverage is not None and coverage >= rules["high_coverage_days"]:
        high = True
        reasons.append("HIGH_STOCK_COVERAGE")
    if (
        sales30 == 0
        and sales_complete
        and metrics.get("zero_sales_verified", False)
        and listing_days is not None
        and listing_days >= rules["min_listing_days"]
        and metrics.get("positive_stock_days", 0) >= rules["min_stock_positive_days"]
        and avail is not None
        and avail > 0
        and inventory_fresh
    ):
        high = True
        reasons.append("VERIFIED_ZERO_SALES_WITH_WFS_STOCK")
    if high and avail is not None and avail > 0 and inventory_fresh:
        risk = "high"
    elif coverage is not None and inventory_fresh:
        group_count = len(signals)
        if coverage >= rules["medium_coverage_days"] and group_count >= 1:
            risk = "medium"
            reasons.append("BACKLOG_AND_BUSINESS_SIGNAL")
        elif coverage >= rules["assisted_coverage_days"] and group_count >= 2:
            risk = "medium"
            reasons.append("ASSISTED_BACKLOG_AND_TWO_SIGNALS")

    protected: list[str] = []
    if risk == "medium":
        if (
            rules["enable_new_listing_protection"]
            and listing_days is not None
            and listing_days < rules["new_listing_protection_days"]
        ):
            protected.append("NEW_LISTING_PROTECTION")
        if (
            rules["enable_recovery_protection"]
            and sales7 is not None
            and prev7 is not None
            and prev7 >= rules["recovery_min_units_each_week"]
            and sales7 >= rules["recovery_min_units_each_week"]
            and sales7 * 100 >= prev7 * (100 + rules["sales_recovery_percent"])
        ):
            protected.append("SALES_RECOVERY_PROTECTION")
    candidate = risk in ("high", "medium") and not protected
    suggested: int | None = None
    if (
        sales30 is not None
        and sales_complete
        and avail is not None
        and avail > 0
        and inventory_fresh
    ):
        demand = _ceil(sales30 * Decimal(rules["holding_days"]) / Decimal(30))
        suggested = max(0, min(int(avail), int(avail) - demand - rules["safety_stock_units"]))
    refund_rate = (
        refund_qty * 100 / sales30
        if refund_qty is not None and sales30 is not None and sales30 > 0 and sales_complete
        else None
    )
    margin = (
        profit30 * 100 / revenue30
        if profit30 is not None and revenue30 is not None and revenue30 > 0 and cost_complete
        else None
    )
    return {
        "risk_level": risk if inventory_fresh and avail is not None else "unknown",
        "candidate_status": "auto"
        if candidate
        else "observe"
        if high
        or risk == "medium"
        or protected
        or (coverage is not None and coverage >= rules["assisted_coverage_days"])
        else "review_required"
        if warnings
        else "none",
        "risk_reasons": reasons,
        "business_signal_groups": sorted(signals),
        "business_signals": signals,
        "protections": protected,
        "warnings": warnings,
        "coverage_days": coverage,
        "suggested_qty": suggested,
        "refund_rate_percent": money(refund_rate),
        "margin_30d_percent": money(margin),
        "rule_version": RULE_VERSION,
    }
