"""物流看板: the 8088 ``build_from_daily`` + ``enrich`` port, without a database.

The golden cases are 22 SPs of the 8088 demo on data day 2026-11-02 (every stage and every
exception type that day); ``gold`` is what the 8088 page computed in the browser.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.modules.pmc_logistics.build import build_sps, carrier_tracks, walmart_facts
from app.modules.pmc_logistics.rules import default_rules, enrich_sp

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures_8088_logistics_20261102.json").read_text("utf-8")
)
CASES = FIXTURE["cases"]


def _norm(key, a, b):
    if key == "ex":
        b = [{k: e[k] for k in ("type", "sev", "desc", "since")} for e in b]
    # JS ``deadline && …`` yields "" where Python yields False.
    if isinstance(a, bool) or isinstance(b, bool) or (a in ("", None) and b in (False, None, "")):
        return bool(a), bool(b)
    return a, b


@pytest.mark.parametrize("case", CASES, ids=[c["sp"]["code"] for c in CASES])
def test_enrich_matches_8088(case):
    rules = default_rules([c["sp"] for c in CASES])
    wm = {k: v for c in CASES for k, v in c["wm"].items()}
    view = enrich_sp(
        case["sp"],
        case["track"],
        wm,
        set(FIXTURE["wm_stores"]),
        rules,
        date.fromisoformat(FIXTURE["today"]),
        wm_day=FIXTURE["wm_day"],
    )
    diffs = {}
    for key, gold in case["gold"].items():
        a, b = _norm(key, gold, view.get(key))
        if a != b:
            diffs[key] = (gold, view.get(key))
    assert not diffs


def test_fixture_covers_every_stage_seen_on_the_data_day():
    stages = {c["gold"]["stage"] for c in CASES}
    assert {
        "已发货",
        "已开船",
        "已到港",
        "派送中",
        "物流签收",
        "Walmart 收货中",
        "Walmart 完成",
    } <= stages


def _cargo(code, *, test=False, sps=("SP1",), status="RECEIVING_IN_PROGRESS"):
    return {
        "cargo_code": code,
        "in_bound_order_id": ("PMC-TEST-" if test else "AQD-") + code,
        "shipping_list_codes": list(sps),
        "distribution_addresses": "1 Main St, Atlanta, GA, US, , 30301",
        "logistics_code": "ATL1",
        "cargo_status": status,
        "store_id": "s1",
        "store_name": "店铺一",
        "cargo_create_date": "2026-09-01 10:00:00",
        "to_receive_time": "",
        "to_closed_time": "",
        "cargo_good_list": [{"msku": "M-1", "sku": "S1", "gtin": "0001", "declare_num": 10}],
    }


def _sp(code, *, created="2026-09-01 08:00:00", tracking="ZY1", cargo="C1"):
    return {
        "shipping_code": code,
        "gmt_create": created,
        "shipping_status": "已发货",
        "creator": "测试",
        "warehouse_id": "1",
        "logistics_provider_id": "6995",
        "logistics_channel_id": "100",
        "logistics_code": "ATL1",
        "head_fee_type": "按计费重",
        "shipping_remark": "",
        "delivery_time": "2026-09-02 00:00:00",
        "actual_delivery_time": "",
        "sail_time": "1970-01-01",
        "expected_arrival_time": "",
        "arrival_time": "",
        "actual_due_ime": "",
        "shipping_logistics": [{"tracking_number": tracking, "transportation_cost": "12.5"}],
        "shipping_goods": [
            {
                "cargo_code": cargo,
                "store_id": "s1",
                "store_name": "店铺一",
                "msku": "M-1",
                "sku": "S1",
                "shipments_num": "10",
                "box_num": "2",
                "total_gw": "8.5",
            }
        ],
        "shipping_first_lets": [],
    }


CHANNEL = {
    "id": "100",
    "name": "美东直航",
    "provider_id": "6995",
    "provider_name": "众壹物流",
    "is_enable": "1",
    "method_name": "海卡",
    "remark": "仓库代码：ATL1 渠道代码：ZY-E1",
}


def test_build_excludes_test_and_pre_window_sps_and_reads_channel_remark():
    lists = [_sp("SP1"), _sp("SP-OLD", created="2026-06-30 23:59:59"), _sp("SP-T", cargo="CT")]
    cargos = [_cargo("C1"), _cargo("CT", test=True, sps=("SP-T",))]
    inputs = build_sps(lists, cargos, [CHANNEL])
    assert [s["code"] for s in inputs.sps] == ["SP1"]
    assert inputs.excluded_test_sps == 1
    sp = inputs.sps[0]
    assert (sp["provider"], sp["channel"], sp["method"]) == ("众壹物流", "美东直航", "海卡")
    assert (sp["chan_fc"], sp["chan_code"]) == ("ATL1", "ZY-E1")
    assert sp["region"] == "美东" and sp["t"]["sail"] == ""
    assert sp["cost"]["transport"] == 12.5 and sp["gw"] == 8.5
    assert sp["cargos"][0]["declare"] == 10 and sp["goods"][0]["gtin"] == "0001"


def test_carrier_tracks_match_by_tracking_then_customer_number_once_per_sp():
    sps = build_sps(
        [_sp("SP1"), _sp("SP2", tracking="", cargo="C2")],
        [_cargo("C1"), _cargo("C2", sps=("SP2",))],
        [CHANNEL],
    ).sps
    orders = [
        {"number": "ZY1", "customerNumber": "C1", "status": "运输中", "totalWeightKg": "30"},
        {"number": "ZY2", "customerNumber": "C2", "status": "签收", "totalWeightKg": "5"},
        {"number": "ZY3", "customerNumber": "C2", "status": "签收", "totalWeightKg": "5"},
    ]
    tracks = [
        {"orderNumber": "ZY2", "trackTime": "2026-09-20 10:00:00", "name": "签收完成"},
        {"orderNumber": "ZY2", "trackTime": "2026-09-10 10:00:00", "name": "已开船"},
        {
            "orderNumber": "ZY1",
            "trackTime": "2026-09-05 10:00:00",
            "name": "预计到港时间为美国时间2026-09-25",
        },
    ]
    out = carrier_tracks(sps, orders, tracks)
    assert out["SP1"]["number"] == "ZY1" and out["SP1"]["nodes"]["eta"] == "2026-09-25"
    assert out["SP2"]["number"] == "ZY2"  # ZY3 also points at C2 but SP2 is taken
    assert (
        out["SP2"]["nodes"]["atd"] == "2026-09-10"
        and out["SP2"]["nodes"]["delivered"] == "2026-09-20"
    )
    assert out["SP2"]["tracks"][0]["cn"] == "签收完成"


def test_walmart_future_delivery_is_not_a_signature():
    shipments = [
        {
            "store_id": "s1",
            "shipmentId": "C1",
            "status": "AWAITING_DELIVERY",
            "actualDeliveryDate": "2026-11-05T00:00:00Z",
            "receivedUnits": "0",
        },
        {
            "store_id": "s1",
            "shipmentId": "C2",
            "status": "RECEIVING_IN_PROGRESS",
            "actualDeliveryDate": "2026-10-20T00:00:00Z",
            "receivedUnits": "8",
        },
    ]
    receipts = [
        {
            "store_id": "s1",
            "shipmentId": "C2",
            "transactionTime": "2026-10-22T03:00:00Z",
            "changedUnits": "5",
        },
        {
            "store_id": "s1",
            "shipmentId": "C2",
            "transactionTime": "2026-10-21T03:00:00Z",
            "changedUnits": "3",
        },
    ]
    wm, stores = walmart_facts(shipments, receipts, "2026-11-02")
    assert stores == {"s1"}
    assert wm["C1"]["actualDelivery"] == ""
    assert (wm["C2"]["firstReceipt"], wm["C2"]["lastReceipt"], wm["C2"]["receiptUnits"]) == (
        "2026-10-21",
        "2026-10-22",
        8,
    )
