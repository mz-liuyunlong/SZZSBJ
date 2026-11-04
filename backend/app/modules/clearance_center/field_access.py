"""Field-level financial disclosure control for clearance read responses.

Clearance risk classification remains deterministic, but users without the
existing Daily Sales financial permissions never receive cost/profit formula
components or explanatory financial signals.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def mask_clearance_financials(
    data: dict[str, Any],
    *,
    can_view_profit: bool,
    can_view_margin: bool,
) -> dict[str, Any]:
    """Mask sensitive calculations in one clearance Listing detail or list."""
    result = deepcopy(data)
    if "items" in result and isinstance(result["items"], list):
        result["items"] = [
            mask_clearance_financials(
                row, can_view_profit=can_view_profit, can_view_margin=can_view_margin
            )
            for row in result["items"]
        ]
        return result

    if "current" in result and isinstance(result["current"], dict):
        result["current"] = mask_clearance_financials(
            result["current"],
            can_view_profit=can_view_profit,
            can_view_margin=can_view_margin,
        )
    if "current_case" in result and isinstance(result["current_case"], dict):
        result["current_case"] = mask_clearance_financials(
            result["current_case"],
            can_view_profit=can_view_profit,
            can_view_margin=can_view_margin,
        )
    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict):
        return result

    if not can_view_profit:
        evaluation["stock_capital_usd"] = None
        evaluation["unit_cost_usd"] = None
        evaluation["business_signals"] = {}
        evaluation["business_signal_groups"] = []
        evaluation["warnings"] = [
            reason for reason in evaluation.get("warnings", [])
            if not str(reason).startswith("PROFIT_")
        ]
        evaluation["cost_complete"] = None
    if not (can_view_profit and can_view_margin):
        evaluation["margin_30d_percent"] = None
    return result
