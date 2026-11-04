"""Fail-closed new-product financial field filtering shared by API readers."""

from __future__ import annotations

from typing import Any

from app.core.auth import Principal
from app.core.permissions import has_permission
from app.modules.data_pages.field_access import (
    ORDER_PROFIT_GROSS_PROFIT_PERMISSION,
    ORDER_PROFIT_MARGIN_PERMISSION,
)


def redact_new_product_metrics(metrics: dict[str, Any], principal: Principal) -> dict[str, Any]:
    """Apply the established order-profit grants to the same MART-derived fields.

    Do not mutate the source dict: callers may re-use it for authorized reads.
    Derived score/launch outcomes can disclose restricted margins indirectly.
    """
    can_profit = has_permission(principal, ORDER_PROFIT_GROSS_PROFIT_PERMISSION)
    can_margin = can_profit and has_permission(principal, ORDER_PROFIT_MARGIN_PERMISSION)
    if can_profit and can_margin:
        return {**metrics, "financial_visibility": "authorized"}

    periods: dict[str, dict[str, Any]] = {}
    for key, original in metrics["periods"].items():
        period = dict(original)
        if not can_profit:
            period["profit"] = None
            for key in ("sp_ad_spend", "sem_ad_spend", "ad_spend", "ad_spend_ratio"):
                if key in period:
                    period[key] = None
        if not can_margin:
            period["margin"] = None
        periods[key] = period

    score = dict(metrics["score"])
    score.update(
        {
            "status": "restricted",
            "score": None,
            "grade": None,
            "provisional_score": None,
            "provisional_grade": None,
        }
    )
    score.pop("components", None)
    score.pop("purchase_preview", None)  # Grade-based range may leak protected margins
    # The pass/fail result also depends on the protected margin.
    launch = {**metrics["launch"], "status": "restricted", "result": None}
    launch.pop("provisional_result", None)
    return {
        **metrics,
        "periods": periods,
        "score": score,
        "launch": launch,
        "financial_visibility": "restricted",
    }
