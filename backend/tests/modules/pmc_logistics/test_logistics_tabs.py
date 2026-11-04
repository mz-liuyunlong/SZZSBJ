"""到货预测 and 货代看板 ports (8088 ``app-b.jsx`` TabForecast / ``zy_panel``), no database.

The forecast golden cases are 24 SPs of the 8088 demo on data day 2026-11-02 that cover every
sellable bucket, 已到·收货中, 已签收未上架 and 未签收已上架; ``gold`` is what the 8088 page
computed in the browser for the product rows those SPs make.
"""

import json
from datetime import date
from pathlib import Path

from app.modules.pmc_logistics.carriers import (
    carrier_orders,
    missing_orders,
    sort_orders,
    zy_provider_ids,
)
from app.modules.pmc_logistics.forecast import forecast_rows, forecast_summary

FC = json.loads((Path(__file__).parent / "fixtures_8088_forecast_20261102.json").read_text("utf-8"))
LINE_KEYS = ("code", "cargo", "bucket", "arr", "arrSrc", "sell", "days", "sign", "shelf")


def test_forecast_matches_8088_rows_and_lines():
    rows = forecast_rows(FC["sps"], FC["wm"], date.fromisoformat(FC["today"]), FC["buffer"])
    got = {r["key"]: r for r in rows}
    assert set(got) == {g["key"] for g in FC["gold"]}
    for gold in FC["gold"]:
        mine = got[gold["key"]]
        for key, value in gold.items():
            if key == "lines":
                assert [{k: x[k] for k in LINE_KEYS} for x in mine["lines"]] == value, gold["key"]
            else:
                assert mine[key] == value, (gold["key"], key)


def test_forecast_fixture_covers_every_bucket():
    summary = forecast_summary(
        forecast_rows(FC["sps"], FC["wm"], date.fromisoformat(FC["today"]), FC["buffer"])
    )
    for key in ("bOver", "b15", "b30", "b60", "b60p", "signedNP", "aShip"):
        assert summary[key] > 0, key


def test_forecast_lookups_and_closed_cargo():
    sp = {
        "code": "SP1",
        "status": "已发货",
        "stage": "已开船",
        "fc": "ATL1",
        "region": "美东",
        "arrivalActual": "",
        "arrivalActualSrc": "",
        "arrivalPlan": "2026-11-20",
        "arrivalPlanSrc": "eta+cycle",
        "arrivalDate": "2026-11-20",
        "cargos": [
            {"code": "C1", "status": "WORKING", "items": []},
            {"code": "C2", "status": "CLOSED", "items": []},
        ],
        "goods": [
            {
                "cargo": "C1",
                "store_id": "s1",
                "store": "店一",
                "msku": "M1",
                "sku": "S1",
                "gtin": "G1",
                "name": "n",
                "qty": 10,
            },
            {
                "cargo": "C2",
                "store_id": "s1",
                "store": "店一",
                "msku": "M2",
                "sku": "S2",
                "gtin": "G2",
                "name": "n",
                "qty": 5,
            },
        ],
    }
    rows = forecast_rows(
        [sp],
        {"C1": {"byGtin": {"G1": 4}, "itemsRecv": {}, "firstReceipt": "2026-10-30"}},
        date(2026, 11, 2),
        10,
        item_ids={("s1", "M1"): "123"},
        owners={"S1": ["甲", "乙"]},
    )
    assert [r["key"] for r in rows] == ["s1|M1"]
    r = rows[0]
    assert (r["item_id"], r["owner"]) == ("123", "甲、乙")
    # ≥1 unit shelved with nothing signed → 已到·收货中 and 未签收已上架
    assert (r["total"], r["aShip"], r["aShelf"], r["anom"]) == (0, 10, 4, 1)
    assert r["lines"][0]["bucket"] == "已到·收货中" and r["lines"][0]["sell"] == "2026-10-30"
    no_shelf = forecast_rows([sp], {}, date(2026, 11, 2), 10)[0]
    assert (no_shelf["b30"], no_shelf["nextSell"]) == (10, "2026-11-30")


def _sp(code, tracking, cargo, provider="6995", status="已发货"):
    return {
        "code": code,
        "status": status,
        "provider_id": provider,
        "tracking": tracking,
        "cargos": [{"code": cargo}],
        "store_id": "s1",
        "fc": "ATL1",
        "region": "美东",
        "boxes": 3,
        "created": "2026-09-01",
    }


def test_carrier_orders_link_by_tracking_then_cargo_and_flag_stale():
    sps = [_sp("SP1", ["ZY1"], "C1"), _sp("SP2", [], "C2"), _sp("SP3", ["ZY9"], "C3")]
    orders = [
        {"number": "ZY1", "customerNumber": "X", "status": "已开船", "totalWeightKg": "30"},
        {"number": "ZY1", "customerNumber": "dup", "status": "已签收"},
        {"number": "ZY2", "customerNumber": "C2", "status": "已签收", "volume": "1.5"},
    ]
    tracks = [
        {"orderNumber": "ZY1", "trackTime": "2026-10-20 08:00:00", "name": "已开船"},
        {"orderNumber": "ZY1", "trackTime": "2026-10-01 08:00:00", "name": "货物进入操作中心"},
        {"orderNumber": "ZY2", "trackTime": "2026-10-01 08:00:00", "name": "签收完成"},
    ]
    out = carrier_orders(sps, orders, tracks, {"s1": "店一"}, date(2026, 11, 2))
    by = {o["number"]: o for o in out}
    assert by["ZY1"]["sp"] == "SP1" and by["ZY1"]["status"] == "已开船"  # first row wins
    assert by["ZY1"]["trackCn"] == "已开船" and by["ZY1"]["staleDays"] == 13
    assert by["ZY1"]["stale"] is True and by["ZY1"]["store"] == "店一"
    assert by["ZY2"]["sp"] == "SP2" and by["ZY2"]["stale"] is False  # signed is never stale
    assert [o["number"] for o in sort_orders(out)] == ["ZY1", "ZY2"]

    not_found, no_tracking, queried, zy_sps = missing_orders(
        sps, {"ZY1", "ZY2"}, zy_provider_ids({"6995": "众壹物流"}), {"s1": "店一"}
    )
    assert [x["tracking"] for x in not_found] == ["ZY9"]
    assert [x["sp"] for x in no_tracking] == ["SP2"]
    assert (queried, zy_sps) == (2, 3)
