"""The committed V4 snapshot is read, not rescored/persisted, on the GET path."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.new_products.v4_evidence_projection import attach_v4_saved_evidence


def specimen():
    row = {
        "facts": {"valid_units_14d": "19", "valid_orders_14d": 17,
                  "effective_orders_14d": 17, "first_order_day": 3},
        "evaluation": {"observation_state": "automatic_partial", "rule_version": 0,
                       "dimensions": {"speed": "7.00", "trust": "7.30", "ad": "5.18", "profit": "0.73"}},
    }
    perf = SimpleNamespace(
        sales_units=Decimal("19"), sales_orders=17,
        metric_window_start_la=date(2026, 10, 9),
        metric_window_end_la=date(2026, 10, 22),
    )
    proof = {
        "auto_dimension_scores": {"rule_version": 0, "scoring_provenance": "PR337_SOURCE_REBUILD_V4",
                                  "dimensions": {"speed": "7.00", "trust": "7.30", "ad": "5.18", "profit": "0.73"},
                                  "automatic_points": "3.2", "covered_weight_pct": "85"},
        "speed_history_full": {"status": "scored", "source": "fact_walmart_order_items",
            "window_start_la": "2026-10-09", "window_end_la": "2026-10-22", "rule_version": 0,
            "first_order_day": 3, "effective_orders_14d": 10,
            "order_fact_orders": 10, "mart_orders": 17, "score": "7.00"},
        "trust_history_full": {"status": "scored", "source": "fact_walmart_order_items",
            "window_start_la": "2026-10-09", "window_end_la": "2026-10-22", "rule_version": 0,
            "valid_units_14d": "11", "valid_orders_14d": 10, "single_unit_orders_14d": 9,
            "mart_units": "19", "mart_orders": 17, "score": "7.30"},
    }
    return row, perf, proof


def test_real_v4_yc00656_proof_overrides_mart_display_only():
    row, perf, proof = specimen()
    orig = deepcopy(proof)
    attach_v4_saved_evidence(row, perf, proof)
    assert row["facts"]["effective_orders_14d"] == 10
    assert row["facts"]["first_order_day"] == 3
    assert row["facts"]["valid_units_14d"] == "11"
    assert row["facts"]["valid_orders_14d"] == 10
    assert row["facts"]["single_unit_orders_14d"] == 9
    assert row["facts"]["auto_scoring_provenance"] == "PR337_SOURCE_REBUILD_V4"
    assert row["evaluation"]["dimensions"]["speed"] == "7.00"
    assert row["evaluation"]["dimensions"]["trust"] == "7.30"
    assert proof == orig
    assert perf.sales_orders == 17 and perf.sales_units == 19


@pytest.mark.parametrize("mutation", [
    lambda d: d["trust_history_full"].update(score="8.00"),
    lambda d: d["trust_history_full"].update(single_unit_orders_14d=8),
    lambda d: d["trust_history_full"].update(valid_units_14d="12"),
    lambda d: d["trust_history_full"].update(mart_orders=10),
    lambda d: d["trust_history_full"].update(mart_units="11"),
    lambda d: d["trust_history_full"].update(window_end_la="2026-10-23"),
    lambda d: d["trust_history_full"].update(source="unknown"),
    lambda d: d["trust_history_full"].update(rule_version=1),
    lambda d: d["trust_history_full"].update(valid_orders_14d=0),
])
def test_unverified_trust_never_promotes(mutation):
    row, perf, proof = specimen()
    mutation(proof)
    attach_v4_saved_evidence(row, perf, proof)
    assert "single_unit_orders_14d" not in row["facts"]
    assert row["facts"]["valid_units_14d"] == "19"
    assert row["facts"]["valid_orders_14d"] == 17


@pytest.mark.parametrize("mutation", [
    lambda d: d["speed_history_full"].update(score="9.10"),
    lambda d: d["speed_history_full"].update(effective_orders_14d=17),
    lambda d: d["speed_history_full"].update(first_order_day=4),
    lambda d: d["speed_history_full"].update(order_fact_orders=17),
    lambda d: d["speed_history_full"].update(window_start_la="2026-10-08"),
])
def test_unverified_speed_does_not_promote(mutation):
    row, perf, proof = specimen()
    mutation(proof)
    attach_v4_saved_evidence(row, perf, proof)
    assert row["facts"]["effective_orders_14d"] == 17


def test_no_v4_provenance_no_projection():
    row, perf, proof = specimen()
    proof["auto_dimension_scores"]["scoring_provenance"] = "LEGACY"
    attach_v4_saved_evidence(row, perf, proof)
    assert row["facts"]["valid_orders_14d"] == 17
    assert "single_unit_orders_14d" not in row["facts"]


def test_frozen_or_custom_rule_never_overwrites():
    for mode in ("frozen", "custom"):
        row, perf, proof = specimen()
        if mode == "frozen":
            row["evaluation"]["observation_state"] = "frozen"
        else:
            row["evaluation"]["rule_version"] = 1
        attach_v4_saved_evidence(row, perf, proof)
        assert row["facts"]["valid_orders_14d"] == 17
        assert "single_unit_orders_14d" not in row["facts"]


def test_does_not_score_without_documented_window():
    row, perf, proof = specimen()
    perf.metric_window_start_la = None
    attach_v4_saved_evidence(row, perf, proof)
    assert "single_unit_orders_14d" not in row["facts"]


def test_full_persisted_api_projection_has_trust_and_speed_breakdowns():
    """Regression for the actual frontend's scoringFacts JSON field names."""
    from app.modules.new_products.persisted_projection import merge_persisted_page_row
    row, perf, proof = specimen()
    fields = (
        "first_wfs_available_date_la", "first_order_date_la", "sales_amount_usd",
        "ad_spend_usd", "ad_clicks", "ad_sales_usd", "roi", "profit_margin_pct",
        "profit_usd", "return_rate_units_pct", "return_rate_orders_pct",
        "calculated_at", "data_status",
    )
    for key in fields:
        setattr(perf, key, None)
    perf.first_wfs_available_date_la = date(2026, 10, 9)
    perf.first_order_date_la = date(2026, 10, 11)
    perf.data_coverage_json = proof
    registry = SimpleNamespace(category_l1=None, category_l2=None, listing_date_la=None)
    row["listing"] = {}
    row["evaluation"]["missing"] = []
    merge_persisted_page_row(row, (registry, perf), date(2026, 11, 14))
    assert row["evaluation"]["dimensions"]["speed"] == "7.00"
    assert row["evaluation"]["dimensions"]["trust"] == "7.30"
    assert row["facts"]["effective_orders_14d"] == 10
    assert row["facts"]["valid_orders_14d"] == 10
    assert row["facts"]["single_unit_orders_14d"] == 9
    assert row["facts"]["valid_units_14d"] == "11"
