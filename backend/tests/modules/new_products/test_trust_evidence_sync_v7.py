"""Guardrails for post-publication trusted order evidence: no DB changes in tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.new_products.trust_evidence_sync import (
    _CANDIDATES,
    _ORDERS,
    _UPDATE,
    sync_saved_trust_evidence,
    verified_evidence,
)


def sample(*, units=20, orders=18, singles=16, trust="9.911111111111111111111111111"):
    row = {
        "registry_id": "11111111-1111-1111-1111-111111111111",
        "account": "primary",
        "store": "S",
        "item": "20881463249",
        "first_wfs": date(2026, 10, 19),
        "start_day": date(2026, 10, 19),
        "end_day": date(2026, 11, 1),
        "saved_units": Decimal(str(units)),
        "saved_orders": orders,
        "calculated_at": datetime(2026, 11, 15, tzinfo=UTC),
        "calculated_marker": "2026-11-15 00:00:00+00",
        "rule_version_id": None,
        "active_version": None,
        "rule_config": None,
        "coverage": {"auto_dimension_scores": {"dimensions": {"trust": trust}, "rule_version": 0}},
    }
    origin = {
        "registry_id": row["registry_id"],
        "units": Decimal(str(units)),
        "orders": orders,
        "singles": singles,
        "invalid_lines": 0,
        "missing_refs": 0,
    }
    return row, origin


def test_trust_formula_matches_saved_exact_score():
    row, origin = sample()
    result = verified_evidence(row, origin)
    assert result is not None
    assert result["valid_units_14d"] == "20"
    assert result["valid_orders_14d"] == 18
    assert result["single_unit_orders_14d"] == 16
    assert result["saved_trust_score"] == "9.911111111111111111111111111"
    assert result["verified_match"] == "MATCH"
    assert result["calculated_marker"] == row["calculated_marker"]


def test_one_unit_one_order_is_four_point_three():
    row, origin = sample(units=1, orders=1, singles=1, trust="4.3000")
    assert Decimal(verified_evidence(row, origin)["verified_trust_score"]) == Decimal("4.3")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r, o: o.update({"units": Decimal("21")}),
        lambda r, o: o.update({"orders": 17}),
        lambda r, o: o.update({"invalid_lines": 1}),
        lambda r, o: o.update({"missing_refs": 1}),
        lambda r, o: o.update({"singles": 19}),
        lambda r, o: r["coverage"]["auto_dimension_scores"]["dimensions"].update({"trust": "5"}),
        lambda r, o: r.update({"end_day": date(2026, 11, 2)}),
        lambda r, o: r.update({"first_wfs": date(2026, 11, 2)}),
        lambda r, o: r.update({"saved_orders": None}),
        lambda r, o: r["coverage"]["auto_dimension_scores"].update({"rule_version": 2}),
    ],
)
def test_unverified_source_rule_or_window_is_rejected(mutate):
    row, origin = sample()
    mutate(row, origin)
    assert verified_evidence(row, origin) is None


def test_published_rule_is_respected_when_explicitly_versioned():
    row, origin = sample()
    row["rule_version_id"] = "22222222-2222-2222-2222-222222222222"
    row["active_version"] = 4
    row["coverage"]["auto_dimension_scores"]["rule_version"] = 4
    row["rule_config"] = {
        "confirmedScoring": {
            "trust": {
                "targetUnits": 20,
                "unitsWeight": 60,
                "singleRatioZero": 40,
                "singleRatioFull": 90,
                "singleRatioWeight": 40,
            }
        }
    }
    assert verified_evidence(row, origin)["rule_version"] == 4
    row["active_version"] = 5
    assert verified_evidence(row, origin) is None


def test_historical_evidence_and_final_results_are_sql_protected():
    candidate = str(_CANDIDATES)
    update = str(_UPDATE)
    assert "p.calculated_at >= :after_date" in candidate
    for clause in ["p.score IS NULL", "p.grade IS NULL", "t.final_result IS NULL"]:
        assert clause in candidate
    assert "p.data_coverage_json #>> '{trust_history_full,provenance}'" in candidate
    assert "'trust_evidence_history'" in update
    assert "p.data_coverage_json IS NOT DISTINCT FROM CAST(:old_coverage AS jsonb)" in update
    assert "d.decision IN ('打品成功','打品失败')" in update
    assert "f.is_identity_current IS TRUE" in str(_ORDERS)
    assert "f.is_sample_order IS FALSE" in str(_ORDERS)


class FakeResult:
    def __init__(self, rows=None, rowcount=1):
        self.rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, row, origin, updates=1):
        self.row = row
        self.origin = origin
        self.updated = updates
        self.calls = []

    def scalar(self, statement):
        self.calls.append(str(statement))
        return True

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(sql)
        if sql.startswith("SET LOCAL"):
            return FakeResult()
        if "ORDER BY p.calculated_at" in sql:
            assert "after_date" in params
            return FakeResult([self.row])
        if "WITH wanted AS" in sql:
            assert "registry_id" in params["wanted"]
            return FakeResult([self.origin])
        if sql.lstrip().startswith("UPDATE biz_new_product_performance_current"):
            assert params["registry_id"] == self.row["registry_id"]
            assert "single_unit_orders_14d" in params["proof"]
            return FakeResult(rowcount=self.updated)
        raise AssertionError("UNEXPECTED_QUERY")


def test_batch_executes_one_scoped_order_query_and_one_guarded_update():
    row, origin = sample()
    session = FakeSession(row, origin)
    result = sync_saved_trust_evidence(session, after_date=datetime(2026, 11, 14, tzinfo=UTC))
    assert (result.examined, result.verified, result.written) == (1, 1, 1)
    assert sum("WITH wanted AS" in q for q in session.calls) == 1
    assert (
        sum(
            q.lstrip().startswith("UPDATE biz_new_product_performance_current")
            for q in session.calls
        )
        == 1
    )


def test_dry_run_never_updates():
    row, origin = sample()
    session = FakeSession(row, origin)
    result = sync_saved_trust_evidence(
        session, after_date=datetime(2026, 11, 14, tzinfo=UTC), dry_run=True
    )
    assert result.written == 0 and result.verified == 1
    assert not any(q.lstrip().startswith("UPDATE ") for q in session.calls)


def test_concurrent_change_blocks_commit():
    row, origin = sample()
    with pytest.raises(RuntimeError, match="rollback whole batch"):
        sync_saved_trust_evidence(
            FakeSession(row, origin, updates=0), after_date=datetime(2026, 11, 14, tzinfo=UTC)
        )


def test_rejects_unbounded_batches_or_naive_timestamps():
    row, origin = sample()
    session = FakeSession(row, origin)
    with pytest.raises(ValueError):
        sync_saved_trust_evidence(session, after_date=datetime(2026, 11, 14))
    with pytest.raises(ValueError):
        sync_saved_trust_evidence(
            session, after_date=datetime(2026, 11, 14, tzinfo=UTC), batch_limit=1000
        )
    assert session.calls == []


def test_recalculated_active_score_retains_old_proof():
    candidate = str(_CANDIDATES)
    update = str(_UPDATE)
    assert "p.calculated_at::text AS calculated_marker" in candidate
    assert "post_publication_order_fact_verification_v1" in candidate
    assert "jsonb_build_array(p.data_coverage_json->'trust_history_full')" in update
    assert "jsonb_array_length" in candidate and " < 30" in candidate
    for query in (candidate, str(_ORDERS), update):
        assert "ALTER TABLE" not in query
        assert "DROP TABLE" not in query
        assert "TRUNCATE" not in query
