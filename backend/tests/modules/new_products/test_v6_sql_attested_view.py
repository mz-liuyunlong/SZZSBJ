"""Read-only SQL-attested V6: restore both dimensions only for an exact local row."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.new_products.v5_reconciled_projection import correct_pending_v4_projection
from app.modules.new_products.v6_sql_attested_view import _proof_list, apply_attested_current_view


def fixture():
    row = {
        "listing": {
            "source_account_ref": "audit-account",
            "store_id": "110711146247224320",
            "item_id": "20858150090",
        },
        "facts": {
            "effective_orders_14d": 10,
            "valid_orders_14d": 10,
            "valid_units_14d": "11",
            "single_unit_orders_14d": 9,
            "first_order_day": 3,
        },
        "evaluation": {
            "observation_state": "automatic_partial",
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


def v5(row, perf, coverage):
    assert correct_pending_v4_projection(row, perf, coverage)
    assert row["facts"]["effective_orders_14d"] == 17
    assert row["evaluation"]["dimensions"]["trust"] is None


def test_verified_yc00656_two_scores_and_no_persisted_writes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    row, perf, coverage = fixture()
    original_coverage = deepcopy(coverage)
    v5(row, perf, coverage)
    assert apply_attested_current_view(row, perf, coverage)
    assert row["facts"]["first_order_day"] == 3
    assert row["facts"]["single_unit_orders_14d"] == 15
    assert row["facts"]["valid_orders_14d"] == 17
    assert Decimal(row["evaluation"]["dimensions"]["speed"]).quantize(Decimal("0.01")) == Decimal(
        "9.10"
    )
    assert Decimal(row["evaluation"]["dimensions"]["trust"]).quantize(Decimal("0.01")) == Decimal(
        "9.56"
    )
    assert row["evaluation"]["covered_weight_pct"] == 85
    assert row["evaluation"]["dimensions"]["ad"] == "5.18"
    assert row["evaluation"]["dimensions"]["profit"] == "0.73"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    assert coverage == original_coverage
    assert perf.sales_orders == 17 and perf.sales_units == 19


def test_speed_missing_after_v5_is_restored_only_by_verified_saved_first_date(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    row, perf, coverage = fixture()
    v5(row, perf, coverage)
    row["evaluation"]["dimensions"]["speed"] = None
    row["facts"]["first_order_day"] = None
    assert apply_attested_current_view(row, perf, coverage)
    assert Decimal(row["evaluation"]["dimensions"]["speed"]).quantize(Decimal("0.01")) == Decimal(
        "9.10"
    )


@pytest.mark.parametrize("env", ["production", "prod", "test", ""])
def test_forbidden_environment_is_readonly_noop(monkeypatch, env):
    monkeypatch.setenv("APP_ENV", env)
    row, perf, coverage = fixture()
    v5(row, perf, coverage)
    before = deepcopy(row)
    assert not apply_attested_current_view(row, perf, coverage)
    assert row == before


@pytest.mark.parametrize(
    "failure",
    [
        "frozen",
        "approved",
        "wrong_store",
        "wrong_item",
        "wrong_mart",
        "wrong_fact",
        "missing_date",
        "changed_date",
        "invalid_lines",
        "old_score_unknown",
        "wrong_provenance",
        "bad_manifest",
        "bad_singles",
        "bad_historical",
        "wrong_fact_first",
        "already_scored",
    ],
)
def test_never_fabricate_other_or_inconsistent_scores(monkeypatch, failure):
    monkeypatch.setenv("APP_ENV", "local")
    row, perf, coverage = fixture()
    v5(row, perf, coverage)
    proof = deepcopy(_proof_list())
    if failure == "frozen":
        row["evaluation"]["observation_state"] = "frozen"
    elif failure == "approved":
        row["evaluation"]["observation_state"] = "approved"
    elif failure == "wrong_store":
        row["listing"]["store_id"] = "110711111111111111"
    elif failure == "wrong_item":
        row["listing"]["item_id"] = "99999999999"
    elif failure == "wrong_mart":
        perf.sales_orders = 18
    elif failure == "wrong_fact":
        coverage["rebuild_quality"]["order_fact_orders"] = 11
    elif failure == "missing_date":
        perf.first_order_date_la = None
    elif failure == "changed_date":
        perf.first_order_date_la = date(2026, 10, 18)
    elif failure == "invalid_lines":
        coverage["rebuild_quality"]["invalid_source_lines"] = 1
    elif failure == "old_score_unknown":
        coverage["trust_history_full"]["single_unit_orders_14d"] = None
    elif failure == "wrong_provenance":
        coverage["auto_dimension_scores"]["scoring_provenance"] = "OTHER"
    elif failure == "bad_manifest":
        proof[0]["ambiguous_orders"] = 1
    elif failure == "bad_singles":
        proof[0]["historical_singles"] = 8
    elif failure == "bad_historical":
        proof[0]["historical_orders"] = 8
    elif failure == "wrong_fact_first":
        proof[0]["fact_first"] = "2026-10-05"
    elif failure == "already_scored":
        row["evaluation"]["dimensions"]["trust"] = "3.33"
    before = deepcopy(row)
    assert not apply_attested_current_view(row, perf, coverage, attestations=proof)
    assert row == before, failure
