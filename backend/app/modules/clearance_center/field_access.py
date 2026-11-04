"""Clearance financial data and financial-signal inference access controls."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def mask_clearance_financials(
    data: dict[str, Any],
    *,
    can_view_profit: bool,
    can_view_margin: bool,
) -> dict[str, Any]:
    """Mask amounts and risk classification that reveals undisclosed cost signals."""
    result = deepcopy(data)
    if "items" in result and isinstance(result["items"], list):
        result["items"] = [
            mask_clearance_financials(
                row, can_view_profit=can_view_profit, can_view_margin=can_view_margin
            )
            for row in result["items"]
        ]
        return result

    for nested in ("current", "current_case"):
        if isinstance(result.get(nested), dict):
            result[nested] = mask_clearance_financials(
                result[nested], can_view_profit=can_view_profit,
                can_view_margin=can_view_margin,
            )

    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict):
        return result

    if not can_view_profit:
        for name in (
            "stock_capital_usd", "high_stock_capital", "profit_30d_amount",
            "refund_loss_30d", "unit_cost_usd", "cost_complete",
        ):
            evaluation[name] = None
        original = evaluation.get("business_signals") or {}
        visible = {
            key: value for key, value in original.items()
            if key not in ("PROFIT", "ADS")
        }
        evaluation["business_signals"] = visible
        evaluation["business_signal_groups"] = sorted(visible)
        evaluation["warnings"] = [
            warning for warning in evaluation.get("warnings", [])
            if not str(warning).startswith(("PROFIT_", "COST_"))
        ]
        # A medium result derived from hidden profitability/ads must not
        # disclose that its threshold was crossed through a proxy signal.
        if evaluation.get("risk_level") == "medium" and (
            "PROFIT" in original or "ADS" in original
        ):
            evaluation["risk_level"] = "unknown"
            evaluation["candidate_status"] = "review_required"
            evaluation["risk_reasons"] = []
            evaluation["protections"] = []

    if not (can_view_profit and can_view_margin):
        evaluation["margin_30d_percent"] = None
    return result
