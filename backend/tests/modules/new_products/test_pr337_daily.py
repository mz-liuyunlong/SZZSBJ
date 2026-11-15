"""PR337 daily business contract: observation, proofs, idempotence and protection."""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.new_products.pr337_daily_core import (
    VERSION,
    compute,
    daily_partition,
    window,
)
from app.modules.new_products.pr337_daily_db import plan

START = date(2026, 10, 10)


def day(n, o, u, *, income=10):
    return {
        "day": START + timedelta(days=n - 1),
        "orders": o,
        "units": u,
        "bad_rows": 0,
        "revenue": str(Decimal(income) * u),
        "revenue_bad": 0,
        "profit": str(Decimal(3) * u),
        "purchase": str(Decimal(4) * u),
        "freight": str(Decimal(2) * u),
        "profit_bad": 0,
    }


def proof(rows, start=START, cutoff=START + timedelta(days=13)):
    return compute(first_wfs=start, cutoff=cutoff, mart=rows, ads=[])


def candidate(**overrides):
    base = {
        "final_score": None,
        "final_grade": None,
        "final_result": None,
        "purchase_protected": False,
        "decision_protected": False,
        "review_protected": False,
        "process_status": None,
        "locked_start": START,
        "saved_start": None,
        "saved_begin": None,
        "saved_end": None,
        "saved_orders": None,
        "saved_units": None,
        "saved_first": None,
        "has_performance": False,
        "saved_rule_id": None,
        "coverage": None,
    }
    return {**base, **overrides}


def test_unique_single_orders():
    assert daily_partition(19, 19) == 19
    assert daily_partition(13, 15) is None
    assert daily_partition(2, 3) == 1
    assert daily_partition(1, 5) == 0
    assert daily_partition(3, 5) is None
    assert daily_partition(0, 0) == 0


@pytest.mark.parametrize("n,q", [(-1, 1), (2, 1), (0, 1)])
def test_impossible_daily_data(n, q):
    with pytest.raises(ValueError):
        daily_partition(n, q)


def test_yc00665_correct_mart():
    r = [day(2, 1, 1)] + [day(i, 3, 3) for i in range(3, 9)]
    p = proof(r)
    assert (p["orders"], p["units"], p["singles"]) == (19, 19, 19)
    assert Decimal(p["dimensions"]["speed"]).quantize(Decimal(".01")) == Decimal("9.70")
    assert Decimal(p["dimensions"]["trust"]).quantize(Decimal(".01")) == Decimal("9.70")


def test_yc00697_mart_not_order_v2():
    start = date(2026, 10, 9)
    # Oct 16 = day 8 relative to the locked first-WFS date Oct 9.
    r = [day(7, 2, 3), day(8, 2, 3), day(9, 3, 3), day(10, 3, 3), day(11, 3, 3)]
    p = proof(r, start=start, cutoff=start + timedelta(days=13))
    assert (p["orders"], p["units"], p["singles"]) == (13, 15, 11)
    assert abs(Decimal(p["dimensions"]["speed"]) - Decimal("6.0818")) < Decimal(".005")
    assert abs(Decimal(p["dimensions"]["trust"]) - Decimal("8.0692")) < Decimal(".005")


def test_yc00775_isolated_and_scored():
    rows = [day(4, 2, 3), day(5, 2, 3), day(6, 4, 4), day(7, 4, 4), day(8, 5, 5)]
    p = proof(rows)
    assert (p["orders"], p["units"], p["singles"]) == (17, 19, 15)
    assert Decimal(p["dimensions"]["trust"]).quantize(Decimal(".01")) == Decimal("9.56")


def test_open_observation_day_one_to_fourteen():
    rows = [day(2, 1, 1)]
    for elapsed in (2, 3, 7, 14):
        p = proof(rows, cutoff=START + timedelta(days=elapsed - 1))
        assert p["window_days"] == elapsed
        assert p["orders"] == 1 and p["units"] == 1
        assert p["observation_complete"] == (elapsed == 14)
        assert p["dimensions"]["speed"] is not None
        assert p["dimensions"]["trust"] is not None
    assert window(START, START + timedelta(days=30))[1] == START + timedelta(days=13)


def test_no_mart_rows_is_unknown_not_zero():
    with pytest.raises(ValueError, match="MART_ROWS_UNAVAILABLE"):
        proof([])


def test_ambiguous_singles_suppresses_trust_not_speed():
    p = proof([day(3, 3, 5)])
    assert p["dimensions"]["speed"] is not None
    assert p["dimensions"]["trust"] is None and p["singles"] is None


def test_first_order_timing_is_source_day():
    p = proof([day(8, 1, 1), day(9, 1, 1)])
    assert p["first_order_date"] == "2026-10-17"
    assert p["first_order_day"] == 8


def test_cost_missing_does_not_make_false_profit():
    r = day(2, 2, 2)
    r["profit_bad"] = 1
    p = proof([r])
    assert p["dimensions"]["profit"] is None
    assert p["dimensions"]["speed"] is not None


def test_invalid_mart_day_fails_closed():
    with pytest.raises(ValueError):
        proof([day(2, 2, 2), day(2, 2, 2)])
    with pytest.raises(ValueError):
        proof([day(17, 2, 2)])


def test_approved_frozen_and_unknown_status_protected():
    for field, value in [
        ("final_score", Decimal(5)),
        ("final_grade", "B"),
        ("final_result", "打品成功"),
        ("purchase_protected", True),
        ("decision_protected", True),
        ("review_protected", True),
        ("process_status", "unexpected"),
    ]:
        with pytest.raises(ValueError):
            plan(candidate(**{field: value}), proof([day(2, 2, 2)]), None)


def test_mismatched_saved_wfs_protected():
    with pytest.raises(ValueError, match="WFS_LOCK_CHANGED_REVIEW"):
        plan(candidate(saved_start=START + timedelta(days=1)), proof([day(2, 1, 1)]), None)


def test_same_window_sales_mismatch_protected():
    p = proof([day(2, 1, 1)])
    with pytest.raises(ValueError, match="SAVED_MART_TOTALS_DISAGREE"):
        plan(
            candidate(
                saved_start=START,
                saved_begin=START,
                saved_end=START + timedelta(days=13),
                saved_orders=2,
                saved_units=2,
            ),
            p,
            None,
        )


def test_previous_dimension_snapshot_preserved():
    p = proof([day(2, 1, 1)])
    old = {"auto_dimension_scores": {"dimensions": {"speed": "1"}, "scoring_provenance": "old"}}
    out = plan(candidate(coverage=old), p, None)
    assert out["coverage"]["pr337_daily_original_auto_v1"] == old["auto_dimension_scores"]
    assert (
        out["coverage"]["auto_dimension_scores"]["dimensions"]["speed"]
        != old["auto_dimension_scores"]["dimensions"]["speed"]
    )
    assert old["auto_dimension_scores"]["dimensions"]["speed"] == "1"


def test_idempotent_proof_no_rewrite():
    p = proof([day(2, 1, 1)])
    row = candidate(coverage={})
    once = plan(row, p, None)
    row.update(coverage=once["coverage"], saved_begin=START, saved_end=START + timedelta(days=13))
    assert plan(row, p, None) is None


def test_new_label_without_wfs_created_not_scored():
    assert plan(candidate(locked_start=None), None, None)["status"] == "awaiting_wfs"
    assert plan(candidate(), None, None)["status"] == "awaiting_mart"
    assert plan(candidate(has_performance=True), None, None) is None


def test_stores_distinct_even_same_sku():
    x = candidate(store="A", item="20852223505", sku="YC00665")
    y = candidate(store="B", item="21221421247", sku="YC00665")
    assert (x["store"], x["item"]) != (y["store"], y["item"])


def test_saved_view_uses_only_new_matching_persisted_proof():
    from app.modules.new_products.pr337_daily_view import saved_daily_view

    p = proof([day(2, 2, 3)])
    data = plan(candidate(), p, None)
    reg = SimpleNamespace(source_account_ref="primary", store_id="A", item_id="42")
    perf = SimpleNamespace(
        data_coverage_json=data["coverage"],
        metric_window_start_la=START,
        metric_window_end_la=START + timedelta(days=13),
        first_wfs_available_date_la=START,
        first_order_date_la=START + timedelta(days=1),
        sales_orders=2,
        sales_units=Decimal(3),
        sales_amount_usd=Decimal(30),
        profit_usd=Decimal(9),
        roi=Decimal("0.5"),
        profit_margin_pct=Decimal(30),
        ad_spend_usd=None,
        ad_clicks=None,
        ad_sales_usd=None,
        score=None,
        grade=None,
        data_status="available",
    )
    row = {
        "listing": {"source_account_ref": "primary", "store_id": "A", "item_id": "42"},
        "facts": {"single_unit_orders_14d": 999},
        "evaluation": {
            "dimensions": {
                "speed": None,
                "ad": None,
                "profit": None,
                "trust": None,
                "market": None,
            },
            "observation_state": "automatic_partial",
        },
    }
    assert saved_daily_view(row, (reg, perf))
    assert row["facts"]["single_unit_orders_14d"] == 1
    assert row["evaluation"]["dimensions"]["trust"] == p["dimensions"]["trust"]
    assert row["facts"]["effective_orders_14d"] == 2
    assert row["facts"]["sales_amount_usd"] == "30"
    assert row["facts"]["profit_usd"] == "9"
    bad = copy.deepcopy(row)
    bad["listing"]["item_id"] = "different"
    assert not saved_daily_view(bad, (reg, perf))
    bad = copy.deepcopy(row)
    bad["evaluation"]["observation_state"] = "frozen"
    assert not saved_daily_view(bad, (reg, perf))


def test_saved_view_refuses_stale_or_mismatched_counts():
    from app.modules.new_products.pr337_daily_view import saved_daily_view

    p = proof([day(2, 1, 1)])
    data = plan(candidate(), p, None)
    reg = SimpleNamespace(source_account_ref="primary", store_id="A", item_id="42")
    perf = SimpleNamespace(
        data_coverage_json=data["coverage"],
        metric_window_start_la=START,
        metric_window_end_la=START + timedelta(days=13),
        first_wfs_available_date_la=START,
        first_order_date_la=START + timedelta(days=1),
        sales_orders=2,
        sales_units=Decimal(1),
        sales_amount_usd=None,
        profit_usd=None,
        roi=None,
        profit_margin_pct=None,
        ad_spend_usd=None,
        ad_clicks=None,
        ad_sales_usd=None,
        score=None,
        grade=None,
        data_status="available",
    )
    row = {
        "listing": {"source_account_ref": "primary", "store_id": "A", "item_id": "42"},
        "facts": {},
        "evaluation": {"dimensions": {}, "observation_state": "automatic_partial"},
    }
    assert not saved_daily_view(row, (reg, perf))
    assert row["facts"] == {}


class FakeRows:
    def __init__(self, rows, rowcount=0):
        self.rows = rows
        self.rowcount = rowcount

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(self, candidates, mart, ads=(), watermark=None):
        self.candidates = candidates
        self.mart = mart
        self.ads = ads
        self.watermark = watermark
        self.writes = []
        self.reads = []

    def execute(self, query, params=None):
        from app.modules.new_products.pr337_daily_db import (
            _ADS,
            _CANDIDATES,
            _MART,
            _RULE,
            _WATERMARKS,
        )

        self.reads.append(query)
        if query is _CANDIDATES:
            return FakeRows(self.candidates)
        if query is _MART:
            return FakeRows(self.mart)
        if query is _ADS:
            return FakeRows(self.ads)
        if query is _WATERMARKS:
            if self.watermark is None:
                return FakeRows([])
            return FakeRows(self.watermark)
        if query is _RULE:
            return FakeRows([])
        self.writes.append((query, params))
        return FakeRows([], rowcount=1)

    def scalar(self, query, params=None):
        if "pg_try_advisory_xact_lock" in str(query):
            return True
        if "SELECT updated_at" in str(query):
            return datetime(2026, 11, 15)
        raise AssertionError("unexpected scalar " + str(query))


def fake_yc00665():
    from datetime import datetime

    items = [day(2, 1, 1)] + [day(i, 3, 3) for i in range(3, 9)]
    for row in items:
        row["idx"] = "0"
    c = candidate(
        account="primary",
        store="110689966555011584",
        item="20852223505",
        sku="YC00665",
        msku="YC00665-1A",
        product_name="Sample",
        store_name="Store 1",
        title="Sample",
        image_url=None,
        owner_name="operator",
        category_l2=None,
        listing_start=None,
        registry_id="3d1424d1-4840-4eb6-8b52-6065562fe7a3",
        registered_tag=True,
        has_performance=True,
        saved_start=START,
        saved_begin=START,
        saved_end=START + timedelta(days=13),
        saved_first=START + timedelta(days=1),
        saved_orders=19,
        saved_units=Decimal(19),
        saved_updated=datetime(2026, 11, 14),
        coverage={
            "auto_dimension_scores": {
                "scoring_provenance": "PR337_SOURCE_REBUILD_V4",
                "dimensions": {"speed": "4.51", "trust": "6.70"},
            }
        },
    )
    return c, items


def test_full_job_readonly_existing_14_day_yc00665():
    from app.modules.new_products.pr337_daily_db import run_daily

    candidate, mart = fake_yc00665()
    db = FakeDB([candidate], mart)
    res = run_daily(db, apply=False, cutoff_la=date(2026, 11, 14))
    assert res["outcomes"]["would_write"] == 1
    assert res["examples"][0]["orders"] == 19
    assert res["examples"][0]["trust"] is not None
    assert db.writes == []


def test_full_job_apply_optimistic_update_protected():
    from app.modules.new_products.pr337_daily_db import _UPDATE, run_daily

    candidate, mart = fake_yc00665()
    db = FakeDB([candidate], mart)
    res = run_daily(db, apply=True, cutoff_la=date(2026, 11, 14))
    assert res["outcomes"]["written"] == 1
    updated = [params for query, params in db.writes if query is _UPDATE]
    assert len(updated) == 1
    assert updated[0]["orders"] == 19 and updated[0]["units"] == 19
    import json

    saved = json.loads(updated[0]["coverage"])
    assert saved["pr337_daily_original_auto_v1"]["scoring_provenance"] == "PR337_SOURCE_REBUILD_V4"
    assert saved["auto_dimension_scores"]["scoring_provenance"] == VERSION


def test_full_job_new_label_without_stock_creates_rows_only_on_apply():
    from app.modules.new_products.pr337_daily_db import _INSERT_PERF, _INSERT_REG, run_daily

    c, _ = fake_yc00665()
    c.update(
        registry_id=None,
        has_performance=False,
        locked_start=None,
        saved_start=None,
        saved_begin=None,
        saved_end=None,
        saved_first=None,
        saved_orders=None,
        saved_units=None,
        saved_updated=None,
        coverage=None,
    )
    db = FakeDB([c], [])
    preview = run_daily(db, apply=False, cutoff_la=date(2026, 11, 14))
    assert preview["outcomes"]["would_write"] == 1
    assert not db.writes
    committed = run_daily(db, apply=True, cutoff_la=date(2026, 11, 14))
    assert committed["outcomes"]["registry_created"] == 1
    assert committed["outcomes"]["performance_created"] == 1
    assert committed["outcomes"]["awaiting_evidence"] == 1
    assert [q for q, p in db.writes] == [_INSERT_REG, _INSERT_PERF]


def test_full_job_frozen_product_never_updated():
    from app.modules.new_products.pr337_daily_db import run_daily

    c, mart = fake_yc00665()
    c["purchase_protected"] = True
    db = FakeDB([c], mart)
    r = run_daily(db, apply=True, cutoff_la=date(2026, 11, 14))
    assert r["outcomes"]["APPROVAL_PROTECTED"] == 1
    assert not db.writes


def test_full_job_mature_watermark_required_for_open_window():
    from app.modules.new_products.pr337_daily_db import run_daily

    c, mart = fake_yc00665()
    c.update(
        locked_start=date(2026, 11, 12),
        saved_start=None,
        saved_begin=None,
        saved_end=None,
        saved_orders=None,
        saved_units=None,
        saved_first=None,
    )
    db = FakeDB([c], mart, watermark=[])
    r = run_daily(db, apply=False, cutoff_la=date(2026, 11, 14))
    assert r["outcomes"]["STORE_MART_WATERMARK_PENDING"] == 1
    assert not db.writes
