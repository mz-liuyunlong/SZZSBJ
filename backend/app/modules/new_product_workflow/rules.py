"""Pure new-product scoring and launch evaluation with explicit incomplete outcomes."""

from __future__ import annotations

from datetime import date
from typing import Any

DEFAULT_RULES: dict[str, Any] = {
    "weights": {"market": 15, "order": 30, "ads": 20, "profit": 25, "trust": 10},
    "success_days": 60,
    "min_sales": 200,
    "min_margin": 0,
    "max_acos": 35,
}


def compute_new_product_score(
    *,
    market_score: int | None,
    metrics: dict[str, Any],
    rules: dict[str, Any],
    rule_version: int,
    overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    if market_score is None or not metrics.get("complete"):
        return {"status": "insufficient_data", "grade": None, "rule_version": rule_version}
    sales = metrics.get("sales")
    clicks = metrics.get("clicks")
    acos = metrics.get("acos")
    margin = metrics.get("margin")
    if any(value is None for value in (sales, clicks, acos, margin)):
        return {"status": "insufficient_data", "grade": None, "rule_version": rule_version}
    values = {
        "market": float(market_score),
        "order": min(10.0, float(sales) / 30),
        "ads": max(0.0, min(10.0, (100 - float(acos)) / 10)),
        "profit": max(0.0, min(10.0, (float(margin) + 20) / 5)),
        "trust": 10.0 if metrics["complete"] else 0.0,
    }
    applied = overrides or {}
    if any(key not in ("order", "ads", "profit", "trust") for key in applied):
        raise ValueError("unsupported provisional scoring correction dimension")
    if any(value < 0 or value > 10 for value in applied.values()):
        raise ValueError("provisional correction score must be within 0-10")
    values.update(applied)
    weights = rules.get("weights", DEFAULT_RULES["weights"])
    score = round(sum(values[key] * weights[key] for key in values) / 100, 2)
    grade = (
        "S"
        if score >= 9
        else "A"
        if score >= 8
        else "B"
        if score >= 7
        else "C"
        if score >= 6
        else "D"
    )
    return {
        "status": "provisional",
        "grade": None,
        "score": None,
        "provisional_grade": grade,
        "provisional_score": score,
        "components": values,
        "approved_correction_dimensions": sorted(applied),
        "rule_version": rule_version,
        "note": "Not a formal grade: speed, CPC, CVR, ROI and penalty rules await approval.",
    }


def compute_launch_result(
    *,
    metrics: dict[str, Any],
    rules: dict[str, Any],
    start_date: date | None,
    as_of: date,
) -> dict[str, Any]:
    if start_date is None:
        return {"status": "awaiting_verified_sellable_date", "result": None}
    days = int(rules.get("success_days", 60))
    if (as_of - start_date).days < days:
        return {"status": "observing", "result": None}
    if not metrics.get("complete") or any(
        metrics.get(key) is None for key in ("sales", "margin", "acos")
    ):
        return {"status": "insufficient_data", "result": None}
    success = (
        float(metrics["sales"]) >= float(rules.get("min_sales", 200))
        and float(metrics["margin"]) >= float(rules.get("min_margin", 0))
        and float(metrics["acos"]) <= float(rules.get("max_acos", 35))
    )
    return {"status": "evaluated", "result": "success" if success else "failure"}
