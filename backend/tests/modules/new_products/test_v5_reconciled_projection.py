"""V5: a committed V4 snapshot is never silently relabelled as current FACT."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.modules.new_products.v5_reconciled_projection import correct_pending_v4_projection


def sample(*, state="automatic_partial"):
    row = {
        "facts": {
            "effective_orders_14d": 10,
            "first_order_day": 3,
            "valid_orders_14d": 10,
            "valid_units_14d": "11",
            "single_unit_orders_14d": 9,
        },
        "evaluation": {
            "observation_state": state,
            "rule_version": 0,
            "dimensions": {
                "market": None,
                "speed": "7.00",
                "trust": "7.30",
                "ad": "5.18",
                "profit": "0.73",
            },
            "total": None,
            "grade": None,
            "missing": [],
            "automatic_points": "3.2",
            "covered_weight_pct": 85,
        },
        "suggested_qty": None,
    }
    perf = SimpleNamespace(
        sales_units=Decimal("19"),
        sales_orders=17,
        first_wfs_available_date_la=date(2026, 10, 9),
        first_order_date_la=date(2026, 10, 11),
        metric_window_start_la=date(2026, 10, 9),
        metric_window_end_la=date(2026, 10, 22),
    )
    coverage = {
        "auto_dimension_scores": {
            "scoring_provenance": "PR337_SOURCE_REBUILD_V4",
            "rule_version": 0,
            "dimensions": {"speed": "7.00", "trust": "7.30", "ad": "5.18", "profit": "0.73"},
        },
        "rebuild_quality": {
            "source_consistency": "MART_ORDER_FACT_MISMATCH",
            "rule_version": 0,
            "mart_orders": 17,
            "mart_units": "19",
            "order_fact_orders": 10,
            "order_fact_units": "11",
            "invalid_source_lines": 0,
            "source_date_start_la": "2026-10-09",
            "source_date_end_la": "2026-10-22",
        },
        "speed_history_full": {
            "status": "scored",
            "source": "fact_walmart_order_items",
            "rule_version": 0,
            "score": "7.00",
            "window_start_la": "2026-10-09",
            "window_end_la": "2026-10-22",
            "first_order_day": 3,
            "mart_orders": 17,
            "order_fact_orders": 10,
            "effective_orders_14d": 10,
        },
        "trust_history_full": {
            "status": "scored",
            "source": "fact_walmart_order_items",
            "rule_version": 0,
            "score": "7.30",
            "window_start_la": "2026-10-09",
            "window_end_la": "2026-10-22",
            "mart_orders": 17,
            "mart_units": "19",
            "valid_orders_14d": 10,
            "valid_units_14d": "11",
            "single_unit_orders_14d": 9,
        },
    }
    return row, perf, coverage


def test_yc00656_mart_speed_and_fact_trust_blocked():
    row, perf, coverage = sample()
    prior = deepcopy(coverage)
    assert correct_pending_v4_projection(row, perf, coverage)
    assert row["facts"]["effective_orders_14d"] == 17
    assert row["facts"]["first_order_day"] == 3
    assert row["facts"]["valid_orders_14d"] == 17
    assert row["facts"]["valid_units_14d"] == "19"
    assert row["facts"]["single_unit_orders_14d"] is None
    assert Decimal(row["evaluation"]["dimensions"]["speed"]) == Decimal("9.10")
    assert row["evaluation"]["dimensions"]["trust"] is None
    assert row["evaluation"]["dimensions"]["ad"] == "5.18"
    assert row["evaluation"]["dimensions"]["profit"] == "0.73"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    assert row["evaluation"]["covered_weight_pct"] == 75
    assert coverage == prior, "Source and historic evidence must remain unchanged"
    assert perf.sales_orders == 17 and perf.sales_units == 19


def test_exact_source_or_frozen_does_not_change():
    for mode in (
        "matched",
        "frozen",
        "unknown",
        "manual",
        "custom",
        "legacy",
        "wrong_window",
        "wrong_mart",
    ):
        row, perf, coverage = sample()
        if mode == "matched":
            coverage["rebuild_quality"]["source_consistency"] = "VERIFIED"
        elif mode == "frozen":
            row["evaluation"]["observation_state"] = "frozen"
        elif mode == "unknown":
            row["evaluation"]["observation_state"] = "not_calculated"
        elif mode == "manual":
            row["evaluation"]["observation_state"] = "approved"
        elif mode == "custom":
            row["evaluation"]["rule_version"] = 1
        elif mode == "legacy":
            coverage["auto_dimension_scores"]["scoring_provenance"] = "LEGACY"
        elif mode == "wrong_window":
            perf.metric_window_end_la = date(2026, 10, 23)
        elif mode == "wrong_mart":
            coverage["rebuild_quality"]["mart_orders"] = 16
        expected = deepcopy(row)
        assert correct_pending_v4_projection(row, perf, coverage) is False, mode
        assert row == expected, mode


def test_bad_first_order_evidence_does_not_claim_speed_score():
    row, perf, coverage = sample()
    perf.first_order_date_la = None
    assert correct_pending_v4_projection(row, perf, coverage)
    assert row["facts"]["effective_orders_14d"] == 17
    assert row["evaluation"]["dimensions"]["speed"] is None
    assert row["evaluation"]["dimensions"]["trust"] is None


def test_fact_exceeds_mart_fails_closed():
    row, perf, coverage = sample()
    coverage["rebuild_quality"].update(order_fact_orders=18, order_fact_units="20")
    coverage["speed_history_full"].update(order_fact_orders=18, effective_orders_14d=18)
    coverage["trust_history_full"].update(valid_orders_14d=18, valid_units_14d="20")
    assert correct_pending_v4_projection(row, perf, coverage)
    assert row["facts"]["effective_orders_14d"] is None
    assert row["evaluation"]["dimensions"]["speed"] is None
    assert row["evaluation"]["dimensions"]["trust"] is None


def test_bad_old_v4_score_does_not_override_anything():
    row, perf, coverage = sample()
    coverage["trust_history_full"]["score"] = "9.99"
    prior = deepcopy(row)
    assert not correct_pending_v4_projection(row, perf, coverage)
    assert row == prior


def test_integrated_page_projection_has_corrected_view_when_available():
    from app.modules.new_products.persisted_projection import merge_persisted_page_row

    row, perf, coverage = sample()
    perf.data_coverage_json = coverage
    for key in (
        "first_wfs_available_date_la",
        "sales_amount_usd",
        "ad_spend_usd",
        "ad_clicks",
        "ad_sales_usd",
        "roi",
        "profit_margin_pct",
        "profit_usd",
        "return_rate_units_pct",
        "return_rate_orders_pct",
        "calculated_at",
        "data_status",
    ):
        if not hasattr(perf, key):
            setattr(perf, key, None)
    registry = SimpleNamespace(category_l1=None, category_l2=None, listing_date_la=None)
    row["listing"] = {}
    merge_persisted_page_row(row, (registry, perf), date(2026, 11, 14))
    assert row["facts"]["effective_orders_14d"] == 17
    assert Decimal(row["evaluation"]["dimensions"]["speed"]) == Decimal("9.10")
    assert row["evaluation"]["dimensions"]["trust"] is None
