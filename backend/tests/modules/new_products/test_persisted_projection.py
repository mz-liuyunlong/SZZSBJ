"""Stored score API mapping: pure fake objects, no DB access."""
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.new_products.persisted_projection import (
    load_persisted_page,
    merge_persisted_page_row,
)


def _base():
    return {
        "listing": {"category": None, "launch_date_cn": None},
        "facts": {"first_wfs_available_date_la": None, "data_status": "not_calculated"},
        "evaluation": {
            "total": None, "grade": None, "rule_version": 0,
            "dimensions": {"market": None, "speed": None, "ad": None,
                           "profit": None, "trust": None},
            "missing": ["尚未执行后台评分"],
            "observation_state": "not_calculated",
        },
    }


def _fake_record():
    registry = SimpleNamespace(
        category_l1="Home", category_l2="Kitchen & Dining",
        listing_date_la=date(2026, 10, 20),
    )
    perf = SimpleNamespace(
        data_coverage_json={
            "listing_category": {
                "full_path": "Home > Kitchen & Dining > Fridge Magnets",
                "leaf": "Fridge Magnets",
            },
            "auto_dimension_scores": {
                "dimensions": {
                    "speed": "6.222222", "ad": "0.000000",
                    "profit": None, "trust": "3.50000",
                },
                "automatic_points": "2.566666",
                "covered_weight_pct": "60",
            },
        },
        first_wfs_available_date_la=date(2026, 10, 30),
        first_order_date_la=date(2026, 11, 2),
        sales_orders=3,
        sales_units=Decimal("4.0000"),
        sales_amount_usd=Decimal("45.0100"),
        ad_spend_usd=Decimal("7.0000"),
        ad_clicks=30,
        ad_sales_usd=None,
        roi=Decimal("1.12"),
        profit_margin_pct=Decimal("13.5"),
        profit_usd=Decimal("4"),
        return_rate_units_pct=None,
        return_rate_orders_pct=None,
        metric_window_end_la=date(2026, 11, 11),
        calculated_at=datetime(2026, 11, 12, tzinfo=UTC),
        data_status="partial",
    )
    return registry, perf


def test_ad_zero_is_a_real_score_not_missing_and_final_score_remains_null():
    row = _base()
    merge_persisted_page_row(row, _fake_record(), date(2026, 11, 13))
    assert row["evaluation"]["dimensions"]["ad"] == "0.000000"
    assert row["evaluation"]["dimensions"]["speed"] == "6.222222"
    assert row["evaluation"]["dimensions"]["market"] is None
    assert row["evaluation"]["automatic_points"] == "2.566666"
    assert row["evaluation"]["covered_weight_pct"] == "60"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    assert row["facts"]["ad_spend_usd"] == "7.0000"
    assert row["facts"]["roi"] == "1.12"
    assert row["listing"]["category"] == "Fridge Magnets"
    assert row["listing"]["category_l1"] == "Home"
    assert row["facts"]["first_order_date"] == "2026-11-02"
    assert row["facts"]["data_cutoff_la"] == "2026-11-11"


def test_unknown_score_is_still_null_and_absent_registry_leaves_placeholder():
    original = _base()
    merge_persisted_page_row(original, None, date(2026, 11, 13))
    assert original["evaluation"]["observation_state"] == "not_calculated"
    registry, perf = _fake_record()
    perf.data_coverage_json["auto_dimension_scores"]["dimensions"] = {
        "speed": None, "ad": None, "profit": None, "trust": None
    }
    row = _base()
    merge_persisted_page_row(row, (registry, perf), date(2026, 11, 13))
    assert row["evaluation"]["dimensions"]["ad"] is None
    assert row["evaluation"]["observation_state"] == "insufficient_data"


def test_loader_is_page_scoped_and_does_no_database_write():
    session = MagicMock()
    keys = [("account", "store", "item")]
    registry = SimpleNamespace(
        source_account_ref="account", store_id="store", item_id="item"
    )
    session.execute.return_value.all.return_value = [(registry, None)]
    result = load_persisted_page(session, keys)
    assert keys[0] in result
    assert session.execute.call_count == 1
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_loader_rejects_oversize_before_query():
    session = MagicMock()
    try:
        load_persisted_page(session, [("account", "store", str(i)) for i in range(201)])
    except ValueError:
        pass
    else:
        raise AssertionError("should reject oversize")
    session.execute.assert_not_called()
