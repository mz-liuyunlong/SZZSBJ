"""Synthetic reproductions of read-only production reconciliation statistics.

No prod DB access: dates/totals are from the Nov 15 audit; order IDs are synthetic.
These cases test the exact evidence eligibility needed by local PR337.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

import app.modules.new_products.order_lineage_view as view

LA = ZoneInfo("America/Los_Angeles")
FIRST = date(2026, 10, 10)
LAST = date(2026, 10, 23)

# Each paid date -> order quantity distribution; extra Order V2 orders marked
# separately. Do not allow extra order ID to change SaleStat sale totals.
_CASES = {
    "YC00665": {
        "store": "110689966555011584", "item": "20852223505",
        "start": FIRST, "first": date(2026, 10, 11), "old_fact": (9, 9),
        "paid": {11:[1], 13:[1,1,1], 14:[1], 15:[1], 16:[1,1,1],
                 17:[1,1], 18:[1,1,1,1,1,1,1], 19:[1]},
        "extra": {19:[1]}, "expected": (19, 19, 19),
        "excluded": 0, "inferred": 1,
    },
    "YC00697": {
        "store": "110711149920800256", "item": "20874953767",
        "start": date(2026, 10, 9), "first": date(2026, 10, 16), "old_fact": (11, 13),
        "paid": {16:[1], 17:[1], 18:[1,1], 19:[1,1],
                 20:[1,1,2], 21:[1,1,2], 22:[1]},
        "extra": {12:[1], 14:[1,1,1,1]}, "expected": (13, 15, 11),
        "excluded": 5, "inferred": 0,
    },
    "YC00775": {
        "store": "110711149920800256", "item": "20890053496",
        "start": date(2026, 10, 21), "first": date(2026, 10, 24), "old_fact": (18, 20),
        "paid": {24:[1], 25:[1], 26:[1,1,1,1,2],
                 27:[1,1,1,1,1,1,2], 28:[1,1,1]},
        "extra": {29:[1]}, "expected": (17, 19, 15),
        "excluded": 1, "inferred": 0,
    },
}


def _ts(d: date) -> str:
    return str(int(datetime(d.year, d.month, d.day, 13, tzinfo=LA).timestamp()))


def _case(name: str):
    c = _CASES[name]
    start = c["start"]
    end = start + timedelta(days=13)
    mart = []
    facts = []
    order_num = 0
    for dayno, quantities in sorted(c["paid"].items()):
        day = date(2026, 10, dayno)
        mart.append({"day": day, "order_count": len(quantities), "sales_qty": sum(quantities)})
    merged_days = defaultdict(list)
    for bucket in (c["paid"], c["extra"]):
        for dayno, quantities in bucket.items():
            merged_days[dayno].extend(quantities)
    for dayno, quantities in sorted(merged_days.items()):
        day = date(2026, 10, dayno)
        for qty in quantities:
            order_num += 1
            facts.append({
                "account":"primary", "store":c["store"], "item":c["item"],
                "source_order_id": f"{name}-order-{order_num}",
                "source_order_line_id": f"{name}-line-{order_num}",
                "quantity": Decimal(qty), "source_purchase_at_raw": _ts(day),
                "is_identity_current": order_num % 4 != 0,
                "is_sample_order": False, "order_status_raw": "9",
                "business_date_la": day + timedelta(days=1),
                "cross_item_lineage": False,
            })
    count, units, singles = c["expected"]
    assert sum(m["order_count"] for m in mart)==count
    assert sum(m["sales_qty"] for m in mart)==units
    assert sum(sum(q==1 for q in c["paid"][k]) for k in c["paid"])==singles
    snap = {
        "account": "primary", "store": c["store"], "item": c["item"],
        "start_day": start, "end_day": end,
        "sales_orders": count, "sales_units": Decimal(units),
        "coverage": {
            "auto_dimension_scores":{"scoring_provenance":"PR337_SOURCE_REBUILD_V4","rule_version":0},
            "rebuild_quality":{
                "source_consistency":"MART_ORDER_FACT_MISMATCH",
                "rule_version":0,"invalid_source_lines":0,
                "source_date_start_la":start.isoformat(),
                "source_date_end_la":end.isoformat(),
                "mart_orders":count, "mart_units":units,
                "order_fact_orders":c["old_fact"][0],
                "order_fact_units":c["old_fact"][1],
            },
        },
    }
    row = {
        "listing":{
            "source_account_ref":"primary", "store_id":c["store"], "item_id":c["item"],
        },
        "facts":{
            "first_wfs_available_date_la":start.isoformat(),
            "effective_orders_14d":None, "valid_orders_14d":None, "valid_units_14d":None,
            "single_unit_orders_14d":None,
            "order_reconciliation":{
                "version":"PR337_SALESTAT_PERSISTED_VIEW_V5_20261114",
                "mart_orders":count,"mart_units":str(units),
                "current_fact_orders":c["old_fact"][0],
                "current_fact_units":str(c["old_fact"][1]),
            },
        },
        "evaluation":{
            "observation_state":"automatic_partial", "rule_version":0,
            "dimensions":{"market":None,"speed":None,"trust":None,"ad":"5.18","profit":"0.73"},
            "total":None,"grade":None,"missing":["FACT与MART订单数或销售件数不一致，数据可信度待核实"],
        },
        "suggested_qty":None,
    }
    return c, mart, facts, snap, row


class _Res:
    def __init__(self, rows):
        self.rows = rows
    def mappings(self):
        return iter(self.rows)


class _DB:
    def __init__(self, name, mart, facts, snap):
        c = _CASES[name]
        key = ("primary", c["store"], c["item"])
        self.mart = [dict(account=key[0], store=key[1], item=key[2], **r) for r in mart]
        self.facts = facts
        self.snap = [snap]
        self.calls = []
    def execute(self, stmt, params):
        sql = str(stmt)
        self.calls.append((sql,params))
        if "data_coverage_json AS coverage" in sql:
            return _Res(self.snap)
        if "d.order_count,d.sales_qty" in sql:
            return _Res(self.mart)
        if "source_purchase_at_raw" in sql:
            return _Res(self.facts)
        raise AssertionError("UNKNOWN_QUERY")


def _safe_evaluate(facts, config, version):
    # Runtime scoring formula is exercised in the Mac's real test suite. This
    # instrumented evaluator proves the exact inputs passed to the scorer.
    n, u, singles = (facts.get("valid_orders_14d"), facts.get("valid_units_14d"),
                     facts.get("single_unit_orders_14d"))
    speed = "8.8800" if facts.get("first_order_day") and facts.get("effective_orders_14d") else None
    trust = f"{n}:{u}:{singles}" if all(v is not None for v in (n,u,singles)) else None
    return {"dimensions":{"speed":speed,"trust":trust}}


@pytest.mark.parametrize("name", ["YC00665","YC00697","YC00775"])
def test_three_items_recover_paid_mart_orders_units_and_single_distribution(monkeypatch, name):
    monkeypatch.setenv("APP_ENV","local")
    monkeypatch.setattr(view,"evaluate",_safe_evaluate)
    c, mart, facts, snap, row = _case(name)
    before = deepcopy(row)
    start,end=snap["start_day"],snap["end_day"]
    assert view.verify_window(start,end,mart,facts) is None, "Strict fact != mart"
    filtered = view.verify_mart_paid_sample(start,end,mart,facts)
    assert filtered is not None
    assert (filtered["orders"],filtered["units"],filtered["singles"])==c["expected"]
    assert filtered["excluded_order_v2_orders"]==c["excluded"]
    assert filtered["all_single_day_inferences"]==c["inferred"]
    db=_DB(name,mart,facts,snap)
    view.reconcile_pending_rows(db,[row])
    assert len(db.calls)==3
    assert row["facts"]["valid_orders_14d"]==c["expected"][0]
    assert row["facts"]["valid_units_14d"]==str(c["expected"][1])
    assert row["facts"]["single_unit_orders_14d"]==c["expected"][2]
    assert row["facts"]["first_order_day"]==(c["first"]-c["start"]).days+1
    assert row["evaluation"]["dimensions"]["speed"]=="8.8800"
    assert row["evaluation"]["dimensions"]["trust"]==":".join(map(str,c["expected"]))
    assert row["facts"]["order_reconciliation"]["version"]==view.VERSION
    assert row["facts"]["order_reconciliation"]["decision"]=="MART_PAID_SAMPLE_CHECKED"
    assert row["evaluation"]["dimensions"]["ad"]==before["evaluation"]["dimensions"]["ad"]
    assert row["evaluation"]["dimensions"]["profit"]==before["evaluation"]["dimensions"]["profit"]
    assert row["evaluation"]["total"] is None and row["evaluation"]["grade"] is None
    assert all("INSERT" not in sql.upper() and "UPDATE" not in sql.upper() and
               "DELETE" not in sql.upper() for sql,_ in db.calls)


@pytest.mark.parametrize("name", ["YC00665","YC00697","YC00775"])
def test_changed_daily_paid_order_mix_blocks_trust_but_preserves_speed(monkeypatch, name):
    monkeypatch.setenv("APP_ENV","local")
    monkeypatch.setattr(view,"evaluate",_safe_evaluate)
    c, mart, facts, snap, row = _case(name)
    before = deepcopy(row)
    # Change a SaleStat-positive day's candidate unit distribution, impossible
    # to infer with authority even though MART itself remains valid.
    positive = next(x for x in facts if view.purchase_day(x["source_purchase_at_raw"]) == c["first"])
    positive["quantity"] = Decimal(3)
    db = _DB(name,mart,facts,snap)
    view.reconcile_pending_rows(db,[row])
    assert row["facts"]["effective_orders_14d"]==c["expected"][0]
    assert row["evaluation"]["dimensions"]["speed"]=="8.8800"
    assert row["evaluation"]["dimensions"]["trust"] is None
    assert row["facts"]["single_unit_orders_14d"] is None
    assert row["evaluation"]["dimensions"]["ad"]==before["evaluation"]["dimensions"]["ad"]
    assert row["evaluation"]["dimensions"]["profit"]==before["evaluation"]["dimensions"]["profit"]


def test_frozen_never_changes_and_does_not_read(monkeypatch):
    monkeypatch.setenv("APP_ENV","local")
    c, mart, facts, snap, row = _case("YC00665")
    row["evaluation"]["observation_state"]="frozen"
    before=deepcopy(row)
    db=_DB("YC00665",mart,facts,snap)
    view.reconcile_pending_rows(db,[row])
    assert row==before
    assert db.calls==[]


def test_missing_mart_stays_unknown_not_zero(monkeypatch):
    monkeypatch.setenv("APP_ENV","local")
    c, mart, facts, snap, row = _case("YC00665")
    db=_DB("YC00665",[],facts,snap)
    before=deepcopy(row)
    view.reconcile_pending_rows(db,[row])
    assert row==before


def test_wrong_store_or_item_provenance_does_not_score(monkeypatch):
    monkeypatch.setenv("APP_ENV","local")
    c, mart, facts, snap, row=_case("YC00697")
    row["listing"]["store_id"]="different-store"
    before=deepcopy(row)
    db=_DB("YC00697",mart,facts,snap)
    view.reconcile_pending_rows(db,[row])
    assert row==before


def test_wrong_snapshot_orders_preserves_old_view(monkeypatch):
    monkeypatch.setenv("APP_ENV","local")
    c, mart, facts, snap, row=_case("YC00775")
    snap["sales_orders"]+=1
    before=deepcopy(row)
    db=_DB("YC00775",mart,facts,snap)
    view.reconcile_pending_rows(db,[row])
    assert row==before


@pytest.mark.parametrize("name", ["YC00665","YC00697","YC00775"])
def test_detail_score_uses_same_one_listing_paid_evidence(monkeypatch,name):
    monkeypatch.setenv("APP_ENV", "local")
    c, mart, facts, snap, row = _case(name)
    db=_DB(name,mart,facts,snap)
    proof=view.read_paid_order_summary(
        db, "primary",c["store"],c["item"],
        snap["start_day"],snap["end_day"],mart,
    )
    assert proof is not None
    assert (proof["orders"],proof["units"],proof["singles"])==c["expected"]
    assert len(db.calls)==1
    assert "source_purchase_at_raw" in db.calls[0][0]


def test_detail_score_production_does_not_query(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    c, mart, facts, snap, row = _case("YC00697")
    db=_DB("YC00697",mart,facts,snap)
    result=view.read_paid_order_summary(
        db, "primary",c["store"],c["item"],
        snap["start_day"],snap["end_day"],mart)
    assert result is None and db.calls==[]


def test_detail_score_unknown_source_leaves_mart_speed_unchanged(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    c, mart, facts, snap, row = _case("YC00665")
    db=_DB("YC00665",mart,facts,snap)
    facts[0]["source_purchase_at_raw"]="unknown-time"
    proof=view.read_paid_order_summary(
        db,"primary",c["store"],c["item"],
        snap["start_day"],snap["end_day"],mart)
    assert proof is None
