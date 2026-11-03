"""8088 parity for the read-time board view (no database).

The fixture holds 38 published rows from the 2026-11-02 daily replay and what the 8088 demo
(``app-a.jsx`` ``enrich`` / ``itemRows`` / ``buildExceptions``, ``app-c.jsx`` product
dimension) computed for exactly those rows. Stores are anonymised.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.modules.pmc_wfs.board_view import (
    RULE_FAMILY_BY_TYPE,
    TYPE_APPEAL_URGENT,
    TYPE_CARRIER_SIGNED,
    WfsRules,
    build_exceptions,
    build_view,
    product_views,
)

FIXTURE = Path(__file__).with_name("fixtures_8088_board_20261102.json")
BUCKETS = {
    "bOver": "overdue",
    "b15": "d15",
    "b30": "d30",
    "b60": "d60",
    "b60p": "d60_plus",
    "none": "none",
}
SHIP_FIELDS = {
    "test": "is_test",
    "shipped": "shipped",
    "baseline": "baseline",
    "diff": "diff",
    "boxes": "boxes",
    "eta": "eta",
    "etaSrc": "eta_source",
    "etaSrcL": "eta_source_label",
    "etaPassed": "eta_passed",
    "sellable": "sellable",
    "sellableReal": "sellable_real",
    "shippedOut": "shipped_out",
    "d0": "d0",
    "d0Real": "d0_real",
    "dN": "d_n",
    "external": "external",
    "ageDays": "age_days",
    "region": "region",
    "its": "its_inferred",
    "wmReceiptUnits": "wm_receipt_units",
    "wmReceiving": "wm_receiving",
    "wmDone": "wm_done",
    "delivered_at": "carrier_delivered_at",
}
ITEM_FIELDS = {
    "shipped": "shipped",
    "lxRecv": "lx_received",
    "wmRecv": "wm_received",
    "put": "put_away",
    "dmg": "damaged",
    "normal": "normal",
    "over": "over",
    "abn": "abnormal",
}


@pytest.fixture(scope="module")
def golden():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    today = date.fromisoformat(data["today"])
    views = [build_view(**row, today=today) for row in data["rows"]]
    return data, today, views


def test_fixture_covers_rows(golden):
    data, _, views = golden
    assert len(views) == len(data["expected"]["shipments"]) == 38


def test_shipment_fields_match_8088(golden):
    data, _, views = golden
    expected = {s["code"]: s for s in data["expected"]["shipments"]}
    for view in views:
        want = expected[view.code]
        got = {k: getattr(view, attr) for k, attr in SHIP_FIELDS.items()}
        assert got == {k: want[k] for k in SHIP_FIELDS}, view.code
        assert view.wm_first == (want["wmFirst"] or "")[:10]
        assert view.wm_last == (want["wmLast"] or "")[:10]


def test_item_rows_match_8088(golden):
    data, _, views = golden
    expected = {x["code"]: x["items"] for x in data["expected"]["items"]}
    for view in views:
        got = [{k: getattr(i, a) for k, a in ITEM_FIELDS.items()} for i in view.items]
        assert got == [{k: i[k] for k in ITEM_FIELDS} for i in expected[view.code]], view.code


def test_exceptions_match_8088_including_text(golden):
    data, today, views = golden
    got = [
        (e.type, e.code, e.store_id, e.severity, e.found, e.desc, e.qty, e.source)
        for e in build_exceptions(views, WfsRules(), today)
    ]
    want = [
        (e["type"], e["code"], e["store_id"], e["sev"], e["found"], e["desc"], e["qty"], e["real"])
        for e in data["expected"]["exceptions"]
    ]
    assert got == want
    assert len(want) == 21


def test_product_dimension_matches_8088(golden):
    data, today, views = golden
    want = {p["key"]: p for p in data["expected"]["products"]}
    got = product_views(views, today)
    assert len(got) == len(want) == 64
    for row in got:
        w = want[f"{row.store_id}|{row.item_id}"]
        assert row.mskus == w["mskus"] and row.skus == w["skus"]
        assert (row.ships, row.in_transit, row.signed_not_put, row.receiving) == (
            w["ships"],
            w["inTransit"],
            w["signedNP"],
            w["receiving"],
        )
        assert (row.arrived_shipped, row.arrived_signed, row.arrived_shelved) == (
            w["aShip"],
            w["aSign"],
            w["aShelf"],
        )
        assert row.signed_zero_shelved == w["anom"]
        assert (row.next_eta, row.next_sellable) == (w["next"], w["nextSell"])
        assert {BUCKETS[k]: w[k] for k in BUCKETS} == row.buckets
        assert [(x.code, x.msku, x.bucket) for x in row.lines] == [
            (d["code"], d["msku"], BUCKETS.get(d["bucket"], d["bucket"])) for d in w["detail"]
        ]


def _row(**over):
    base = dict(
        cargo_code="T1WFB",
        store_id="S1",
        store_name="店铺1",
        status="AWAITING_DELIVERY",
        created="2026-10-01 10:00:00",
        to_closed_at=None,
        in_bound_order_id="IND-1",
        shipping_codes=["SP1"],
        goods=[
            {
                "msku": "M1",
                "sku": "K1",
                "gtin": "G1",
                "declare_num": 100,
                "shipments_num": 100,
                "received_num": 0,
                "damaged_qty": 0,
            }
        ],
        derived={"sp_goods": [{"msku": "M1", "shipped": 100, "boxes": 5}], "shipped_out": True},
    )
    base.update(over)
    return base


def test_carrier_signed_but_walmart_not_received():
    today = date(2026, 11, 2)
    derived = {
        "sp_goods": [{"msku": "M1", "shipped": 100, "boxes": 5}],
        "carrier_delivered_at": "2026-10-28 09:00",
    }
    view = build_view(**_row(derived=derived), today=today)
    [exc] = build_exceptions([view], WfsRules(), today)
    assert exc.type == TYPE_CARRIER_SIGNED and exc.severity == "high"
    assert exc.found == "2026-10-31" and exc.source == "real"
    assert RULE_FAMILY_BY_TYPE[exc.type] == "carrier_delivered_unreceived"
    # under the threshold → nothing
    assert build_exceptions([view], WfsRules(delivered_not_signed=6), today) == []


def test_appeal_urgent_and_test_shipments_skipped():
    today = date(2026, 11, 2)
    goods = [
        {
            "msku": "M1",
            "sku": "K1",
            "gtin": "G1",
            "declare_num": 100,
            "shipments_num": 100,
            "received_num": 70,
            "damaged_qty": 0,
        }
    ]
    derived = {
        "sp_goods": [{"msku": "M1", "shipped": 100, "boxes": 5}],
        "walmart_signed_date": "2026-09-16",
    }
    row = _row(status="CLOSED", to_closed_at="2026-09-30T00:00:00+00:00", goods=goods)
    view = build_view(**{**row, "derived": derived}, today=today)
    kinds = [e.type for e in build_exceptions([view], WfsRules(), today)]
    assert kinds == ["已关闭短少", TYPE_APPEAL_URGENT]
    test_view = build_view(
        **{**row, "derived": derived, "in_bound_order_id": "PMC-TEST-1"}, today=today
    )
    assert test_view.is_test and build_exceptions([test_view], WfsRules(), today) == []
