"""Business-approved procurement intervals and fail-closed official grading."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.new_product_workflow.scoring_contract import (
    CONFIRMED_PURCHASE_BANDS,
    candidate_grade,
    formal_policy_gate,
    market_review_readiness,
    normalized_purchase_bands,
    purchase_preview,
    quantity_exception,
)


def test_owner_confirmed_purchase_intervals_are_inclusive() -> None:
    assert CONFIRMED_PURCHASE_BANDS == {
        "S": (400, 600),
        "A": (300, 500),
        "B": (200, 400),
        "C": (150, 250),
        "D": (0, 0),
        "Pass": (0, 0),
    }
    for grade, (low, high) in CONFIRMED_PURCHASE_BANDS.items():
        assert normalized_purchase_bands({})[grade] == (low, high)
        if low:
            assert not quantity_exception(low, grade)
            assert not quantity_exception(high, grade)
            assert quantity_exception(low - 1, grade)
            assert quantity_exception(high + 1, grade)
        else:
            assert purchase_preview(grade, 50)["suggested_qty"] == 0


def test_purchase_suggestion_must_never_escape_band() -> None:
    assert purchase_preview("S", 3)["suggested_qty"] == 400
    assert purchase_preview("A", 900)["suggested_qty"] == 500
    assert purchase_preview("B", 277)["suggested_qty"] == 277
    assert purchase_preview("C", None)["suggested_qty"] is None
    assert purchase_preview(None, 500)["status"] == "awaiting_grade"
    with pytest.raises(ValueError):
        normalized_purchase_bands({"purchase_bands": {"D": [1, 10]}})


def test_unapproved_grade_and_roi_cannot_be_silently_published() -> None:
    assert candidate_grade(7.85) == "B"
    assert formal_policy_gate({})["status"] == "blocked"
    assert "historical_grade_conflict" in formal_policy_gate({})
    assert formal_policy_gate({}).get("auto_publish") is False


def test_listing_age_30_day_market_review_gate() -> None:
    today = date(2026, 11, 4)
    assert market_review_readiness(date(2026, 10, 5), today_la=today)["status"] == (
        "ready_for_market_review"
    )
    assert market_review_readiness(date(2026, 10, 6), today_la=today)["status"] == (
        "observation_not_yet_30_days"
    )
    assert market_review_readiness(None, today_la=today)["status"] == ("listing_date_unverified")
