"""Regression suite for new-product financial field-level isolation."""

from __future__ import annotations

from copy import deepcopy

from app.core.auth import Principal
from app.modules.new_product_workflow.field_access import redact_new_product_metrics


def _sample() -> dict:
    return {
        "periods": {
            "30": {"sales": 12, "profit": 40, "margin": 18, "acos": 15},
            "60": {"sales": 22, "profit": 60, "margin": 20, "acos": 18},
        },
        "score": {
            "status": "provisional",
            "provisional_score": 8.6,
            "provisional_grade": "A",
            "components": {"profit": 8, "market": 9},
        },
        "launch": {"status": "evaluated", "result": "success"},
        "inventory": {"available": 100},
    }


def test_view_permission_cannot_reveal_profit_margin_or_derived_grade() -> None:
    data = _sample()
    original = deepcopy(data)
    user = Principal(
        user_id="viewer",
        permissions=frozenset({"page:products:new-product-analysis:view"}),
    )
    result = redact_new_product_metrics(data, user)
    assert result["periods"]["30"]["sales"] == 12
    assert result["periods"]["30"]["profit"] is None
    assert result["periods"]["30"]["margin"] is None
    assert result["score"]["status"] == "restricted"
    assert result["score"]["provisional_score"] is None
    assert "components" not in result["score"]
    assert result["launch"] == {"status": "restricted", "result": None}
    assert data == original


def test_profit_only_permission_does_not_disclose_margin_or_grade() -> None:
    user = Principal(
        user_id="profit-viewer",
        permissions=frozenset({"field:sales:order-profit:gross-profit"}),
    )
    result = redact_new_product_metrics(_sample(), user)
    assert result["periods"]["30"]["profit"] == 40
    assert result["periods"]["30"]["margin"] is None
    assert result["score"]["provisional_grade"] is None


def test_existing_profit_and_margin_grants_preserve_all_values() -> None:
    user = Principal(
        user_id="finance-viewer",
        permissions=frozenset(
            {
                "field:sales:order-profit:gross-profit",
                "field:sales:order-profit:profit-margin",
            }
        ),
    )
    result = redact_new_product_metrics(_sample(), user)
    assert result["periods"]["30"]["margin"] == 18
    assert result["score"]["provisional_grade"] == "A"
    assert result["launch"]["result"] == "success"


def test_super_admin_preserves_existing_values() -> None:
    result = redact_new_product_metrics(
        _sample(), Principal(user_id="admin", permissions=frozenset({"*"}))
    )
    assert result["financial_visibility"] == "authorized"
    assert result["periods"]["60"]["profit"] == 60
