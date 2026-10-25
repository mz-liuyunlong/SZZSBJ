"""Synthetic grading demo tests; no database or external services."""

from datetime import date
from decimal import Decimal

import pytest

from scripts.listing_grade_demo import demo_result

CUTOFF = date(2026, 10, 20)


@pytest.mark.parametrize(
    ("scenario", "grade", "weighted"),
    [
        ("a", "A", "20"),
        ("b", "B", "12"),
        ("c", "C", "7"),
        ("d", "D", "2"),
        ("zero-sales-loss", "D", None),
        ("pending", "待评级", None),
        ("excluded", "不参与评级", None),
    ],
)
def test_synthetic_grades_use_canonical_engine(
    scenario: str, grade: str, weighted: str | None
) -> None:
    result = demo_result(scenario, cutoff=CUTOFF)
    assert result["grade"] == grade
    # Decimal output may retain a meaningful scale (e.g. "7.00" vs "7").
    # This test checks the numeric calculation, not the serialization style.
    if weighted is None:
        assert result["weighted_margin_percent"] is None
    else:
        value = result["weighted_margin_percent"]
        assert value is not None
        assert Decimal(str(value)) == Decimal(weighted)
    assert result["writes_performed"] is False
    assert result["data_source"] == "SYNTHETIC_ONLY"
    assert result["cutoff_la"] == "2026-10-20"


def test_no_upstream_proof_is_not_a_valid_financial_day() -> None:
    result = demo_result("pending", cutoff=CUTOFF)
    assert result["valid_days_short"] == 0
    assert result["valid_days_medium"] == 0
    assert len(result["invalid_dates"]) == 14
    assert result["grade"] == "待评级"


def test_confirmed_zero_sales_with_loss_is_special_d_not_fake_margin() -> None:
    result = demo_result("zero-sales-loss", cutoff=CUTOFF)
    assert result["grade"] == "D"
    assert result["valid_days_short"] == 7
    assert result["valid_days_medium"] == 14
    assert result["sales_short"] == "0"
    assert result["profit_short"] == "-35"
    assert result["weighted_margin_percent"] is None


def test_unknown_demo_case_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown synthetic scenario"):
        demo_result("real-listing", cutoff=CUTOFF)
