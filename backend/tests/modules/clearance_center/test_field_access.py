"""Clearance RBAC: money, inferential signals and per-account isolation."""
from __future__ import annotations

from app.modules.clearance_center.field_access import mask_clearance_financials


def _listing() -> dict:
    return {
        "listing": {"item_id": "A", "source_account_ref": "ACCOUNT-A"},
        "evaluation": {
            "risk_level": "medium",
            "candidate_status": "auto",
            "stock_capital_usd": "2400",
            "high_stock_capital": True,
            "profit_30d_amount": "-90",
            "refund_loss_30d": "10",
            "unit_cost_usd": "12",
            "margin_30d_percent": "-3.5",
            "cost_complete": True,
            "business_signal_groups": ["PROFIT", "AFTER_SALES"],
            "business_signals": {
                "PROFIT": ["LOW_MARGIN_30D"],
                "AFTER_SALES": ["HIGH_PERIOD_REFUND_RATE"],
            },
            "risk_reasons": ["BACKLOG_AND_BUSINESS_SIGNAL"],
            "protections": [],
            "warnings": ["PROFIT_COST_INCOMPLETE", "LISTING_START_UNKNOWN"],
        },
    }


def test_without_financial_permission_does_not_leak_profit_classification() -> None:
    result = mask_clearance_financials(
        _listing(), can_view_profit=False, can_view_margin=False
    )
    evaluation = result["evaluation"]
    for key in (
        "stock_capital_usd", "high_stock_capital", "profit_30d_amount",
        "unit_cost_usd", "margin_30d_percent", "refund_loss_30d",
    ):
        assert evaluation[key] is None
    assert evaluation["business_signal_groups"] == ["AFTER_SALES"]
    assert evaluation["risk_level"] == "unknown"
    assert evaluation["candidate_status"] == "review_required"
    assert evaluation["risk_reasons"] == []
    assert "PROFIT_COST_INCOMPLETE" not in evaluation["warnings"]


def test_financial_permission_with_missing_margin_permission() -> None:
    result = mask_clearance_financials(
        _listing(), can_view_profit=True, can_view_margin=False
    )
    assert result["evaluation"]["profit_30d_amount"] == "-90"
    assert result["evaluation"]["margin_30d_percent"] is None


def test_nested_approval_detail_is_masked_recursively() -> None:
    source = _listing()
    result = mask_clearance_financials(
        {"current_case": {"current": source}},
        can_view_profit=False, can_view_margin=False,
    )
    assert (
        result["current_case"]["current"]["evaluation"]["profit_30d_amount"] is None
    )
    assert source["evaluation"]["profit_30d_amount"] == "-90"
