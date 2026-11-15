from datetime import date

from app.modules.new_products.evaluation_policy import eligible, evaluation_status, fourteen_days


def test_first_stock_day_is_inclusive():
    first = date(2026, 11, 1)
    assert not fourteen_days(first, date(2026, 11, 13))
    assert fourteen_days(first, date(2026, 11, 14))


def test_three_independent_triggers():
    first = date(2026, 11, 1)
    assert eligible(
        first_wfs=first, cutoff=date(2026, 11, 5), sold_status=None, sold_day=None, manual=True
    ) == (True, "manual")
    assert eligible(
        first_wfs=first, cutoff=date(2026, 11, 5), sold_status="verified", sold_day="2026-11-05"
    ) == (True, "auto_sold_out")
    assert eligible(
        first_wfs=first, cutoff=date(2026, 11, 14), sold_status=None, sold_day=None
    ) == (True, "auto_14d")
    assert eligible(
        first_wfs=first, cutoff=date(2026, 11, 5), sold_status="unverified", sold_day="2026-11-05"
    ) == (False, "OBSERVATION_IN_PROGRESS")


def test_no_order_is_not_a_missing_listing_date():
    assert (
        evaluation_status(
            listing_date="2026-11-01", first_wfs=None, coverage={}, grade=None, total=None
        )
        == "测评中"
    )
    assert (
        evaluation_status(listing_date=None, first_wfs=None, coverage={}, grade=None, total=None)
        == "待到货"
    )


def test_final_grade_is_persistent_and_not_inferred():
    assert (
        evaluation_status(listing_date=None, first_wfs=None, coverage={}, grade="D", total="1.00")
        == "测评未通过"
    )
    assert (
        evaluation_status(
            listing_date="2026-11-01",
            first_wfs=None,
            coverage={
                "evaluation_formal_trigger": {"status": "completed"},
                "auto_dimension_scores": {"dimensions": {}},
            },
            grade=None,
            total=None,
        )
        == "待市场评分"
    )
