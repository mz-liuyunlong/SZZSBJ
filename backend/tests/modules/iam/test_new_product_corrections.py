"""Safety contracts for the independent score correction workflow."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.auth import Principal
from app.modules.new_product_workflow.router import (
    ScoreCorrectionDecision,
    ScoreCorrectionWrite,
    _financial_correction_allowed,
)
from app.modules.new_product_workflow.rules import DEFAULT_RULES, compute_new_product_score


def test_score_correction_requires_evidence_and_bounded_numeric_value() -> None:
    with pytest.raises(ValidationError):
        ScoreCorrectionWrite(
            expected_version=3,
            dimension="order",
            target_score=11,
            reason="同意调整",
        )
    with pytest.raises(ValidationError):
        ScoreCorrectionWrite(
            expected_version=3,
            dimension="ads",
            target_score=5,
            reason="      ",
        )
    assert (
        ScoreCorrectionDecision(decision="rejected", note="没有符合条件的原始记录").decision
        == "rejected"
    )


def test_profit_adjustment_requires_existing_field_permissions() -> None:
    p = Principal(user_id="user-1", permissions=frozenset({"*"}))
    viewer = Principal(user_id="viewer", permissions=frozenset())
    assert _financial_correction_allowed(p, "profit")
    assert not _financial_correction_allowed(viewer, "profit")
    assert _financial_correction_allowed(viewer, "order")


def test_approved_override_remains_provisional_and_bounds_enforced() -> None:
    metrics = {"complete": True, "sales": 180, "clicks": 100, "acos": 30, "margin": 12}
    score = compute_new_product_score(
        market_score=8,
        metrics=metrics,
        rules=DEFAULT_RULES,
        rule_version=3,
        overrides={"order": float(Decimal("7.5"))},
    )
    assert score["status"] == "provisional"
    assert score["grade"] is None
    assert score["components"]["order"] == 7.5
    assert score["approved_correction_dimensions"] == ["order"]
    with pytest.raises(ValueError):
        compute_new_product_score(
            market_score=8,
            metrics=metrics,
            rules=DEFAULT_RULES,
            rule_version=3,
            overrides={"profit": 11},
        )
