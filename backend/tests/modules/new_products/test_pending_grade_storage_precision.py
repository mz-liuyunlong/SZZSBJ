"""Regression: persisted NUMERIC(10,4) vs exact JSONB grade snapshot."""
from decimal import Decimal

import pytest

from app.modules.new_products.evaluation_workflow import _stored_grade_matches_snapshot
from app.modules.new_products.models import NewProductPerformanceCurrent


def test_saved_score_column_has_four_decimal_places():
    assert NewProductPerformanceCurrent.__table__.c.score.type.scale == 4


@pytest.mark.parametrize(
    ("persisted", "exact"),
    [
        ("6.8735", "6.873456789"),
        ("6.1235", "6.123450000"),
        ("6.8734", "6.873400001"),
        ("0.0000", "0.00000000"),
        ("10.0000", "10.00000"),
    ],
)
def test_postgres_numeric_4_round_trip_is_not_a_business_conflict(persisted, exact):
    assert _stored_grade_matches_snapshot("B", Decimal(persisted), {
        "grade": "B", "total": exact,
    })


@pytest.mark.parametrize(
    ("stored_grade", "stored_total", "snapshot"),
    [
        ("B", Decimal("6.8734"), {"grade": "B", "total": "6.873456789"}),
        ("C", Decimal("6.8735"), {"grade": "B", "total": "6.873456789"}),
        ("B", Decimal("6.8735"), {"grade": "B", "total": "NaN"}),
        ("B", Decimal("6.8735"), {"grade": "B", "total": None}),
        ("B", None, {"grade": "B", "total": "6.873456789"}),
        ("B", Decimal("6.8735"), None),
    ],
)
def test_real_score_changes_or_invalid_snapshots_still_block(
    stored_grade, stored_total, snapshot
):
    assert not _stored_grade_matches_snapshot(stored_grade, stored_total, snapshot)


def test_pending_and_final_confirm_use_the_same_storage_guard():
    import inspect

    from app.modules.new_products import evaluation_workflow
    from app.modules.new_products.service import NewProductService

    pending = inspect.getsource(evaluation_workflow.publish_after_market)
    confirmed = inspect.getsource(NewProductService.confirm_grade)
    assert "not _stored_grade_matches_snapshot(perf.grade, perf.score, frozen)" in pending
    assert "not _stored_grade_matches_snapshot(perf.grade, perf.score, final)" in confirmed
    assert "same_total" not in pending
    assert "NP_EVAL_PENDING_MARKET_VERSION" in pending
    assert "NP_GRADE_CONFIRM_REVISION_CONFLICT" in confirmed
