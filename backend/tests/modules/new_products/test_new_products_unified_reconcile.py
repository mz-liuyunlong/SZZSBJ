"""Local read-only new-product reconciliation: historical versions, dates and safety."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.modules.new_products.order_lineage_view import (
    VERSION,
    _reconstruct,
    purchase_day,
    reconcile_pending_rows,
    verify_window,
)

START = date(2026, 10, 9)
END = date(2026, 10, 22)
KEY = ("primary", "110711146247224320", "20858150090")
LA = ZoneInfo("America/Los_Angeles")


def _stamp(d: date, hour: int = 13) -> str:
    return str(int(datetime(d.year, d.month, d.day, hour, 0, tzinfo=LA).timestamp()))


def _order_rows(*, extra=False, changed_version=False, cross_item=False):
    rows = []
    # 15 one-unit orders + two two-unit orders = 17 orders / 19 units.
    # Seven history-only identities; the current ten are all current markers.
    dates = [
        date(2026, 10, 11),
        date(2026, 10, 12),
        date(2026, 10, 13),
        date(2026, 10, 14),
        date(2026, 10, 15),
        date(2026, 10, 16),
        date(2026, 10, 17),
        date(2026, 10, 18),
        date(2026, 10, 18),
        date(2026, 10, 19),
        date(2026, 10, 19),
        date(2026, 10, 20),
        date(2026, 10, 20),
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 22),
        date(2026, 10, 22),
    ]
    quantities = [1] * 17
    quantities[4], quantities[7] = 2, 2
    for i, (d, q) in enumerate(zip(dates, quantities, strict=True)):
        r = {
            "account": KEY[0],
            "store": KEY[1],
            "item": KEY[2],
            "source_order_id": f"order{i:02d}",
            "source_order_line_id": f"line{i:02d}",
            "quantity": Decimal(q),
            "source_purchase_at_raw": _stamp(d),
            "is_identity_current": i >= 7,
            "is_sample_order": False,
            "order_status_raw": "9",
            "business_date_la": d + timedelta(days=1),
            "cross_item_lineage": bool(cross_item and i == 0),
        }
        rows.append(r)
        if i < 7:
            old = dict(r)
            old["business_date_la"] = d + timedelta(days=2)
            if changed_version and i == 0:
                old["quantity"] = Decimal(2)
            rows.append(old)
    rows.append(
        {
            **rows[-1],
            "source_order_id": "outside",
            "source_order_line_id": "outside",
            "source_purchase_at_raw": _stamp(date(2026, 10, 25)),
            "quantity": Decimal(1),
        }
    )
    if extra:
        rows.append(
            {
                **rows[-1],
                "source_order_id": "extra",
                "source_order_line_id": "extra",
                "source_purchase_at_raw": _stamp(date(2026, 10, 19)),
            }
        )
    return rows


def _mart(rows):
    buckets = defaultdict(lambda: [0, 0])
    unique = {}
    for r in rows:
        oid = r["source_order_id"]
        if oid not in unique:
            unique[oid] = (purchase_day(r["source_purchase_at_raw"]), int(r["quantity"]))
    for d, qty in unique.values():
        if START <= d <= END:
            buckets[d][0] += 1
            buckets[d][1] += qty
    # Ignore "extra" order in generated MART so its presence is an evidence conflict.
    if "extra" in unique:
        d, q = unique["extra"]
        buckets[d][0] -= 1
        buckets[d][1] -= q
    return [
        {
            "account": KEY[0],
            "store": KEY[1],
            "item": KEY[2],
            "day": d,
            "order_count": n,
            "sales_qty": Decimal(q),
        }
        for d, (n, q) in sorted(buckets.items())
    ]


def _projection():
    return {
        "listing": {"source_account_ref": KEY[0], "store_id": KEY[1], "item_id": KEY[2]},
        "facts": {
            "first_wfs_available_date_la": START.isoformat(),
            "effective_orders_14d": 17,
            "valid_orders_14d": 17,
            "valid_units_14d": "19",
            "single_unit_orders_14d": None,
            "order_reconciliation": {
                "version": "PR337_SALESTAT_PERSISTED_VIEW_V5_20261114",
                "mart_orders": 17,
                "mart_units": "19",
                "current_fact_orders": 10,
                "current_fact_units": "11",
            },
        },
        "evaluation": {
            "observation_state": "automatic_partial",
            "rule_version": 0,
            "dimensions": {
                "market": None,
                "speed": None,
                "trust": None,
                "ad": "5.18",
                "profit": "0.73",
            },
            "total": None,
            "grade": None,
            "missing": ["FACT与MART订单数或销售件数不一致，数据可信度待核实"],
        },
        "suggested_qty": None,
    }


def _snapshot():
    return {
        "account": KEY[0],
        "store": KEY[1],
        "item": KEY[2],
        "start_day": START,
        "end_day": END,
        "sales_orders": 17,
        "sales_units": Decimal(19),
        "coverage": {
            "auto_dimension_scores": {
                "scoring_provenance": "PR337_SOURCE_REBUILD_V4",
                "rule_version": 0,
            },
            "rebuild_quality": {
                "source_consistency": "MART_ORDER_FACT_MISMATCH",
                "rule_version": 0,
                "invalid_source_lines": 0,
                "source_date_start_la": START.isoformat(),
                "source_date_end_la": END.isoformat(),
                "mart_orders": 17,
                "mart_units": "19",
                "order_fact_orders": 10,
                "order_fact_units": "11",
            },
        },
    }


class _Mapped:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class _ReadSession:
    def __init__(self, facts=None, mart=None, snap=None):
        self.facts = facts if facts is not None else _order_rows()
        self.mart = mart if mart is not None else _mart(_order_rows())
        self.snap = snap if snap is not None else [_snapshot()]
        self.calls = []

    def execute(self, stmt, params):
        sql = str(stmt)
        self.calls.append((sql, params))
        if "data_coverage_json AS coverage" in sql:
            return _Mapped(self.snap)
        if "d.order_count,d.sales_qty" in sql:
            return _Mapped(self.mart)
        if "source_purchase_at_raw" in sql:
            return _Mapped(self.facts)
        raise AssertionError("Unexpected SQL call")


def test_epoch_seconds_and_millis_and_china_text():
    assert purchase_day("1791737469") == date(2026, 10, 11)
    assert purchase_day("1791737469000") == date(2026, 10, 11)
    assert purchase_day(datetime(2026, 10, 12, 0, 0)) == date(2026, 10, 11)
    assert purchase_day("1970") is None
    assert purchase_day("invalid") is None
    assert purchase_day(None) is None


def test_historical_versions_exact_match_and_out_of_window_excluded():
    factual = _order_rows()
    verified = verify_window(START, END, _mart(factual), factual)
    assert verified == {"orders": 17, "units": 19, "singles": 15, "first_date": date(2026, 10, 11)}
    assert _reconstruct(START, END, factual)[date(2026, 10, 11)] == (1, 1, 1)


@pytest.mark.parametrize(
    "broken",
    [
        "dup_qty",
        "cross_item",
        "extra",
        "duplicate_mart",
        "unknown_time",
        "invalid_status",
        "missing_id",
        "mart_missing",
    ],
)
def test_uncertain_sources_must_not_create_scores(broken):
    facts = _order_rows(
        changed_version=broken == "dup_qty",
        cross_item=broken == "cross_item",
        extra=broken == "extra",
    )
    mart = _mart(_order_rows())
    if broken == "duplicate_mart":
        mart.append(dict(mart[0]))
    elif broken == "unknown_time":
        facts[0]["source_purchase_at_raw"] = "UNPARSEABLE"
    elif broken == "invalid_status":
        facts[0]["order_status_raw"] = "CANCELED"
    elif broken == "missing_id":
        facts[0]["source_order_line_id"] = None
    elif broken == "mart_missing":
        mart = []
    assert verify_window(START, END, mart, facts) is None, broken


def test_one_extra_single_order_does_not_discard_paid_sales(monkeypatch):
    # On a paid 2 orders/2 units day, every candidate is one unit, so the
    # MART-paid single-unit ratio is uniquely determined despite one extra ID.
    monkeypatch.setenv("APP_ENV", "local")
    row = _projection()
    s = _ReadSession(facts=_order_rows(extra=True))
    reconcile_pending_rows(s, [row])
    assert len(s.calls) == 3
    assert row["facts"]["order_reconciliation"]["version"] == VERSION
    assert row["facts"]["order_reconciliation"]["all_single_day_inferences"] == 1
    assert row["facts"]["valid_orders_14d"] == 17
    assert row["facts"]["single_unit_orders_14d"] == 15
    assert row["evaluation"]["dimensions"]["speed"] is not None
    assert row["evaluation"]["dimensions"]["trust"] is not None


def test_unresolved_mixed_quantity_surplus_blocks_trust_but_not_mart_speed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    row = _projection()
    before = deepcopy(row)
    physical = _order_rows(extra=True)
    physical[-1]["quantity"] = Decimal(2)  # Same-day mixture cannot infer singles.
    s = _ReadSession(facts=physical)
    reconcile_pending_rows(s, [row])
    assert row["evaluation"]["dimensions"]["speed"] is not None
    assert row["evaluation"]["dimensions"]["trust"] is None
    assert row["facts"]["effective_orders_14d"] == 17
    assert row["facts"]["valid_units_14d"] == "19"
    assert row["facts"]["single_unit_orders_14d"] is None
    assert row["evaluation"]["dimensions"]["ad"] == before["evaluation"]["dimensions"]["ad"]
    assert row["evaluation"]["dimensions"]["profit"] == before["evaluation"]["dimensions"]["profit"]
    assert row["evaluation"]["total"] is None


def test_single_page_reconcile_succeeds_without_writing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    row = _projection()
    s = _ReadSession()
    reconcile_pending_rows(s, [row])
    assert len(s.calls) == 3
    assert row["facts"]["order_reconciliation"]["version"] == VERSION
    assert row["facts"]["effective_orders_14d"] == 17
    assert row["facts"]["single_unit_orders_14d"] == 15
    assert row["facts"]["observation_first_order_date_la"] == "2026-10-11"
    assert Decimal(str(row["evaluation"]["dimensions"]["speed"])).quantize(
        Decimal(".01")
    ) == Decimal("9.10")
    assert Decimal(str(row["evaluation"]["dimensions"]["trust"])).quantize(
        Decimal(".01")
    ) == Decimal("9.56")
    assert row["evaluation"]["dimensions"]["ad"] == "5.18"
    assert row["evaluation"]["dimensions"]["profit"] == "0.73"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    assert all("INSERT" not in sql.upper() and "UPDATE" not in sql.upper() for sql, _ in s.calls)


@pytest.mark.parametrize(
    "mode",
    [
        "frozen",
        "approved",
        "custom_rule",
        "wrong_provenance",
        "other_item",
        "production",
        "missing_mart",
        "changed_snapshot",
    ],
)
def test_final_and_nonverified_rows_unchanged(monkeypatch, mode):
    monkeypatch.setenv("APP_ENV", "production" if mode == "production" else "local")
    row = _projection()
    snap = _snapshot()
    if mode == "frozen":
        row["evaluation"]["observation_state"] = "frozen"
    elif mode == "approved":
        row["evaluation"]["observation_state"] = "approved"
    elif mode == "custom_rule":
        row["evaluation"]["rule_version"] = 1
    elif mode == "wrong_provenance":
        snap["coverage"]["auto_dimension_scores"]["scoring_provenance"] = "unknown"
    elif mode == "other_item":
        row["listing"]["item_id"] = "999999"
    elif mode == "missing_mart":
        snap["sales_orders"] = None
    elif mode == "changed_snapshot":
        snap["coverage"]["rebuild_quality"]["mart_orders"] = 16
    before = deepcopy(row)
    sess = _ReadSession(snap=[snap])
    reconcile_pending_rows(sess, [row])
    assert row == before, mode
