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
        == "待测评确认"
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


def test_late_first_order_speed_is_zero():
    from types import SimpleNamespace

    from app.modules.new_products.unified_publish import _reconcile_mart_evidence

    key = ("account", "store", "item")
    cutoff = date(2026, 11, 18)
    facts = {
        "first_wfs_available_date_la": date(2026, 11, 1),
        "first_order_day": 18,
        "effective_orders_14d": None,
        "valid_orders_14d": 1,
        "valid_units_14d": 1,
        "trust_order_units_ratio_pct": 100,
        "zero_sales_verified": False,
    }
    snapshot = SimpleNamespace(daily={}, ads={})

    _reconcile_mart_evidence(
        facts,
        key,
        snapshot,
        {
            "first_order_date": "2026-11-18",
            "sales_units": 1,
            "ad_spend_usd": 2,
            "status": "scored",
        },
        {("account", "store"): cutoff},
        cutoff,
    )

    assert facts["effective_orders_14d"] == 0
    assert facts["first_order_day"] is None
    assert facts["zero_sales_verified"] is False
    assert facts["valid_orders_14d"] == 1
    assert facts["valid_units_14d"] == 1
    assert facts["trust_order_units_ratio_pct"] == 100


def test_late_first_order_without_sync_does_not_invent_zero():
    from types import SimpleNamespace

    from app.modules.new_products.unified_publish import _reconcile_mart_evidence

    key = ("account", "store", "item")
    facts = {
        "first_wfs_available_date_la": date(2026, 11, 1),
        "effective_orders_14d": None,
        "first_order_day": None,
    }

    _reconcile_mart_evidence(
        facts,
        key,
        SimpleNamespace(daily={}, ads={}),
        {"first_order_date": "2026-11-18", "sales_units": 1},
        {},
        date(2026, 11, 18),
    )

    assert facts["effective_orders_14d"] is None
