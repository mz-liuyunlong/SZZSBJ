"""Persisted PR337 read-mapping regression tests; no DB connection."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.modules.new_products.persisted_read import snapshot_row


def test_saved_auto_dimensions_category_and_metrics_are_returned_without_grade():
    registry = SimpleNamespace(category_l1="Home", category_l2="Kitchen & Dining")
    performance = SimpleNamespace(
        data_coverage_json={
            "cutoff_la": "2026-11-11",
            "listing_category": {
                "full_path": "Home > Kitchen & Dining > Fridge Magnets",
                "leaf": "Fridge Magnets",
            },
            "auto_dimension_scores": {
                "rule_version": 0,
                "dimensions": {"speed": "6.5", "ad": None, "profit": "0", "trust": "7.6"},
                "covered_weight_pct": "65",
                "automatic_weighted_points": "2.7127",
            },
        },
        first_wfs_available_date_la=date(2026, 11, 1),
        first_order_date_la=date(2026, 11, 2),
        metric_window_start_la=date(2026, 11, 1),
        metric_window_end_la=date(2026, 11, 11),
        roi=Decimal("1.23"),
        profit_margin_pct=Decimal("25"),
        ad_spend_usd=None,
        ad_clicks=None,
        ad_sales_usd=None,
        sales_units=Decimal("15"),
        sample_units=None,
        sales_orders=12,
        sales_amount_usd=Decimal("300"),
        profit_usd=Decimal("75"),
        returned_units=None,
        returned_orders=None,
        return_rate_units_pct=None,
        return_rate_orders_pct=None,
        acos_pct=None,
        data_status="available",
        grade=None,
        score=None,
    )
    listing = SimpleNamespace(
        first_wfs_available_date_la=None,
        model_dump=lambda **kwargs: {
            "source_account_ref": "acc",
            "store_id": "s",
            "item_id": "i",
            "category": None,
        },
    )
    result = snapshot_row(listing, None, (registry, performance), None, date(2026, 11, 13))
    assert result["listing"]["category"] == "Fridge Magnets"
    assert result["listing"]["category_path"].startswith("Home >")
    assert result["evaluation"]["dimensions"]["speed"] == "6.5"
    assert result["evaluation"]["dimensions"]["profit"] == "0"
    assert result["evaluation"]["dimensions"]["ad"] is None
    assert result["evaluation"]["grade"] is None
    assert result["evaluation"]["total"] is None
    assert result["facts"]["roi"] == "1.23"
    assert result["facts"]["automatic_covered_weight_pct"] == "65"
    assert result["evaluation"]["observation_state"] == "calculated"


def test_missing_snapshot_is_not_an_invented_zero_score():
    listing = SimpleNamespace(
        first_wfs_available_date_la=None,
        model_dump=lambda **kwargs: {
            "source_account_ref": "acc",
            "store_id": "s",
            "item_id": "i",
            "category": None,
        },
    )
    result = snapshot_row(listing, None, None, None, date(2026, 11, 13))
    assert result["evaluation"]["observation_state"] == "not_calculated"
    assert all(x is None for x in result["evaluation"]["dimensions"].values())
    assert result["facts"]["data_status"] == "not_calculated"
