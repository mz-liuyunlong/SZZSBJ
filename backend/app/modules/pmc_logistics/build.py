"""Build the 8088 物流看板 inputs (``build_from_daily.py``) from stored source records.

Pure functions over the same records the 8088 build reads from the daily folder: Lingxing
shipping lists / WFS cargos / logistics channels (ODS ``payload_json``), carrier orders and
tracks (众壹) and Walmart inbound shipments / items / Receipt log. No I/O, no API calls.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

WINDOW_FROM: Final = "2026-07-01"  # 8088 v3 (Rocky 2026-09-23): SPs created from July on
TEST_PREFIX: Final = "PMC-TEST-"
STATE_REGION: Final = {
    **dict.fromkeys(("CA", "WA", "OR", "NV", "AZ", "UT"), "美西"),
    **dict.fromkeys(
        (
            "TX", "IN", "MS", "AR", "LA", "IL", "KY", "OH", "MO", "TN", "WI", "MN", "KS",
            "OK", "CO",
        ),
        "美中",
    ),
    **dict.fromkeys(
        ("NJ", "PA", "FL", "GA", "NY", "VA", "NC", "SC", "MD", "MA", "CT"), "美东"
    ),
}  # fmt: skip


def _d(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("1970") or not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return ""
    return text[:10]


def _num(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def test_sets(cargos: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    """Test shipments (``PMC-TEST-`` inbound order) and the SPs that carry them."""

    test_cargos: set[str] = set()
    test_sps: set[str] = set()
    for c in cargos:
        if str(c.get("in_bound_order_id") or "").startswith(TEST_PREFIX):
            test_cargos.add(str(c.get("cargo_code") or ""))
            test_sps.update(str(x) for x in _list(c.get("shipping_list_codes")) if x)
    return test_cargos, test_sps


def _channel(row: Mapping[str, Any]) -> dict[str, str]:
    raw = _obj(row.get("raw_json"))
    return {
        "channel_id": str(row.get("channel_id") or row.get("id") or ""),
        "channel_name": str(row.get("channel_name") or row.get("name") or ""),
        "enabled": str(row.get("enabled") or raw.get("enabled", row.get("is_enable", "")) or ""),
        "provider_id": str(row.get("provider_id") or ""),
        "provider_name": str(row.get("provider_name") or ""),
        "method_name": str(row.get("method_name") or raw.get("method_name", "") or ""),
        "remark": str(row.get("remark") or raw.get("remark", "") or ""),
    }


@dataclass(slots=True)
class LogisticsInputs:
    sps: list[dict[str, Any]]
    fcs: dict[str, dict[str, Any]]
    stores: dict[str, str]
    providers: dict[str, str]
    channels: list[dict[str, str]]
    excluded_test_sps: int = 0
    tracks: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_sps(
    shipping_lists: Iterable[Mapping[str, Any]],
    cargos: Sequence[Mapping[str, Any]],
    channel_rows: Iterable[Mapping[str, Any]],
) -> LogisticsInputs:
    test_cargos, test_sps = test_sets(cargos)
    cargos = [c for c in cargos if str(c.get("cargo_code") or "") not in test_cargos]
    rows = [
        r
        for r in shipping_lists
        if str(r.get("gmt_create") or "")[:10] >= WINDOW_FROM
        and str(r.get("shipping_code") or "") not in test_sps
    ]
    excluded = sum(1 for r in shipping_lists if str(r.get("shipping_code") or "") in test_sps)
    chs = [_channel(r) for r in channel_rows]
    by_channel = {c["channel_id"]: c for c in chs}
    providers: dict[str, str] = {}
    for c in chs:
        providers.setdefault(c["provider_id"], c["provider_name"])

    fcs: dict[str, dict[str, Any]] = {}
    for c in cargos:
        parts = [x.strip() for x in str(c.get("distribution_addresses") or "").split(",")]
        fc = str(c.get("logistics_code") or "")
        if fc and fc not in fcs:
            state = parts[2] if len(parts) > 2 else ""
            fcs[fc] = {
                "fc": fc,
                "addr": parts[0] if parts else "",
                "city": parts[1] if len(parts) > 1 else "",
                "state": state,
                "zip": parts[5] if len(parts) > 5 else "",
                "region": STATE_REGION.get(state, "待定"),
                "n": 0,
            }
        if fc:
            fcs[fc]["n"] += 1

    def meta(cid: str) -> dict[str, str]:
        c = by_channel.get(cid) or {}
        remark = c.get("remark", "") or ""
        m1 = re.search(r"仓库代码[:：]\s*([A-Za-z0-9]+)", remark)
        m2 = re.search(r"渠道代码[:：]\s*([A-Za-z0-9\-]+)", remark)
        name = c.get("channel_name", "") or ""
        method = c.get("method_name", "") or ("快递" if "FedEx" in name or "UPS" in name else "")
        return {
            "channel": name,
            "method": method,
            "enabled": c.get("enabled", ""),
            "chan_fc": m1.group(1) if m1 else "",
            "chan_code": m2.group(1) if m2 else "",
        }

    by_code = {str(c.get("cargo_code") or ""): c for c in cargos}

    def cargo_sum(c: Mapping[str, Any]) -> dict[str, Any]:
        lines = [g for g in _list(c.get("cargo_good_list")) if isinstance(g, dict)]
        return {
            "declare": sum(_num(g.get("declare_num")) for g in lines),
            "received": sum(_num(g.get("received_num")) for g in lines),
            "damaged": sum(_num(g.get("dameged_qty") or g.get("damaged_qty")) for g in lines),
            "items": [
                {
                    "msku": g.get("msku", ""),
                    "sku": g.get("sku", ""),
                    "declare": _num(g.get("declare_num")),
                    "received": _num(g.get("received_num")),
                    "item_id": g.get("item_id") or g.get("walmart_item_id") or "",
                }
                for g in lines
            ],
        }

    stores: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("shipping_code") or "")
        logi = [x for x in _list(r.get("shipping_logistics")) if isinstance(x, dict)]
        goods = [x for x in _list(r.get("shipping_goods")) if isinstance(x, dict)]
        first_lets = [x for x in _list(r.get("shipping_first_lets")) if isinstance(x, dict)]
        gtin_by = {f.get("msku"): f.get("gtin") for f in first_lets}
        head_by = {f.get("msku"): f for f in first_lets}
        cargo_gtin: dict[tuple[str, str], str] = {}
        for g0 in goods:
            c0 = by_code.get(str(g0.get("cargo_code") or ""))
            if c0:
                for x in _list(c0.get("cargo_good_list")):
                    if isinstance(x, dict) and x.get("msku") and x.get("gtin"):
                        cargo_gtin[(str(c0.get("cargo_code")), x["msku"])] = x["gtin"]
        tracking = [
            x.get("tracking_number") or x.get("logistics_number")
            for x in logi
            if x.get("tracking_number") or x.get("logistics_number")
        ]
        cost_t = sum(_float(x.get("transportation_cost")) for x in logi)
        cost_o = sum(_float(x.get("other_cost")) for x in logi)
        exp_t = sum(_float(x.get("expected_transportation_cost")) for x in logi)
        currency = (logi[0].get("transportation_currency") if logi else "") or "USD"
        fc = str(r.get("logistics_code") or "")
        gs: list[dict[str, Any]] = []
        cargo_codes: list[str] = []
        for g in goods:
            cc = str(g.get("cargo_code") or "")
            if cc and cc not in cargo_codes:
                cargo_codes.append(cc)
            if g.get("store_id") and g.get("store_name"):
                stores[str(g["store_id"])] = str(g["store_name"])
            head = head_by.get(g.get("msku")) or {}
            gs.append(
                {
                    "cargo": cc,
                    "store_id": str(g.get("store_id") or ""),
                    "store": g.get("store_name", "") or "",
                    "msku": g.get("msku", "") or "",
                    "sku": g.get("sku", "") or "",
                    "name": g.get("product_name", "") or "",
                    "gtin": cargo_gtin.get((cc, g.get("msku", "")))
                    or gtin_by.get(g.get("msku"), "")
                    or "",
                    "qty": _num(g.get("shipments_num") or g.get("apply_num")),
                    "apply": _num(g.get("apply_num")),
                    "boxes": _num(g.get("box_num")),
                    "per": _num(g.get("quantity_in_case")),
                    "cbm": _float(g.get("cbm")),
                    "gw": _float(g.get("total_gw")),
                    "box": f"{g.get('box_length', '')}×{g.get('box_width', '')}×"
                    f"{g.get('box_height', '')}",
                    "box_kg": g.get("box_gross_weight", ""),
                    "head_cost": _float(head.get("per_first_let_cost")),
                    "value_source": head.get("value_source", ""),
                }
            )
        cg: list[dict[str, Any]] = []
        for cc in cargo_codes:
            c = by_code.get(cc)
            if not c:
                cg.append(
                    {
                        "code": cc,
                        "status": "",
                        "store": "",
                        "received": 0,
                        "declare": 0,
                        "items": [],
                    }
                )
                continue
            cg.append(
                {
                    "code": cc,
                    "status": c.get("cargo_status") or "",
                    "store_id": str(c.get("store_id") or ""),
                    "store": c.get("store_name") or "",
                    "inbound_order_id": c.get("in_bound_order_id") or "",
                    "created": _d(c.get("cargo_create_date")),
                    "to_receive": _d(c.get("to_receive_time")),
                    "to_closed": _d(c.get("to_closed_time")),
                    "fc": c.get("logistics_code") or "",
                    **cargo_sum(c),
                }
            )
        provider_id = str(r.get("logistics_provider_id") or "")
        out.append(
            {
                "code": code,
                "status": r.get("shipping_status") or "",
                "created": _d(r.get("gmt_create")),
                "creator": r.get("creator") or "",
                "wh_id": str(r.get("warehouse_id") or ""),
                "provider_id": provider_id,
                "provider": providers.get(provider_id, ""),
                "channel_id": str(r.get("logistics_channel_id") or ""),
                **meta(str(r.get("logistics_channel_id") or "")),
                "fc": fc,
                "region": (fcs.get(fc) or {}).get("region", "待定"),
                "fee_type": r.get("head_fee_type") or "",
                "remark": r.get("shipping_remark") or "",
                "tracking": tracking,
                "cost": {
                    "transport": round(cost_t, 2),
                    "other": round(cost_o, 2),
                    "currency": currency,
                    "expected_transport": round(exp_t, 2),
                },
                "t": {
                    "delivery": _d(r.get("delivery_time")),
                    "actual_delivery": _d(r.get("actual_delivery_time")),
                    "sail": _d(r.get("sail_time")),
                    "expected_arrival": _d(r.get("expected_arrival_time")),
                    "arrival": _d(r.get("arrival_time")),
                    "actual_due": _d(r.get("actual_due_ime")),  # Lingxing's own spelling
                },
                "stores": sorted({g["store"] for g in gs if g["store"]}),
                "store_id": next((g["store_id"] for g in gs if g["store_id"]), ""),
                "goods": gs,
                "cargos": cg,
                "qty": sum(g["qty"] for g in gs),
                "boxes": sum(g["boxes"] for g in gs),
                "cbm": round(sum(g["cbm"] for g in gs), 3),
                "gw": round(sum(g["gw"] for g in gs), 1),
                "skus": len({g["sku"] for g in gs}),
            }
        )
    return LogisticsInputs(
        sps=out,
        fcs=fcs,
        stores=stores,
        providers=providers,
        channels=chs,
        excluded_test_sps=excluded,
    )


def _date_in(text: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text or "")
    return m.group(1) if m else ""


def carrier_tracks(
    sps: Sequence[Mapping[str, Any]],
    orders: Iterable[Mapping[str, Any]],
    tracks: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """众壹 orders → per-SP track nodes (8088 ``real_tracks``), matched by tracking number,
    then by WFS shipment (customer number); one carrier order per SP."""

    summary: dict[str, Mapping[str, Any]] = {}
    for r in orders:
        summary.setdefault(str(r.get("number") or ""), r)
    events: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for e in tracks:
        events[str(e.get("orderNumber") or "")].append(e)
    by_tracking = {t: s for s in sps for t in s.get("tracking") or []}
    by_cargo = {c["code"]: s for s in sps for c in s.get("cargos") or []}
    used: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for number, r in summary.items():
        sp = by_tracking.get(number) or by_cargo.get(str(r.get("customerNumber") or ""))
        if not sp or sp["code"] in used:
            continue
        used.add(sp["code"])
        evs = events[number]
        newest = sorted(evs, key=lambda x: str(x.get("trackTime") or ""), reverse=True)
        nodes = dict.fromkeys(
            ("etd", "atd", "eta", "ata", "delivered", "out", "opc", "est_delivery"), ""
        )
        for e in sorted(evs, key=lambda x: str(x.get("trackTime") or "")):
            n = str(e.get("name") or "")
            t = str(e.get("trackTime") or "")[:10]
            if (
                n.startswith("官网更新开船时间")
                or n.startswith("船司变更开船时间")
                or "开船时间延" in n
            ):
                d = _date_in(n[6:])
                if d:
                    nodes["etd"] = d
            elif n == "已开船":
                nodes["atd"] = t
            elif (
                n.startswith("预计到港时间")
                or n.startswith("船司变更到港时间")
                or n.startswith("预计延迟到")
            ):
                d = _date_in(n[4:])
                if d:
                    nodes["eta"] = d
            elif n.startswith("已靠港"):
                nodes["ata"] = t
            elif n == "签收完成":
                nodes["delivered"] = t
            elif n.startswith("已装柜"):
                nodes["out"] = t
            elif n == "货物进入操作中心":
                nodes["opc"] = t
            m = re.search(r"预计美国时间\s*(\d{4}-\d{2}-\d{2}).*派送入仓", n)
            if m:
                nodes["est_delivery"] = m.group(1)
        latest = newest[0] if newest else {}
        out[sp["code"]] = {
            "number": number,
            "customerNumber": r.get("customerNumber") or "",
            "status": r.get("status") or "",
            "totalWeightKg": _float(r.get("totalWeightKg")),
            "trackCn": r.get("latestTrackCn") or latest.get("name", "") or "",
            "trackEn": r.get("latestTrackEn") or latest.get("enName", "") or "",
            "lastTrack": str(latest.get("trackTime") or "")[:16],
            "tracks": [
                {
                    "t": str(e.get("trackTime") or "")[:16],
                    "cn": e.get("name") or "",
                    "en": e.get("enName") or "",
                }
                for e in newest
            ],
            "nodes": nodes,
        }
    return out


def walmart_facts(
    shipments: Iterable[Mapping[str, Any]],
    receipts: Iterable[Mapping[str, Any]],
    today_s: str,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Walmart inbound shipments + Receipt log → 8088 ``wm`` facts per shipment id.

    ``shipments`` rows: store_id, shipmentId, status, actualDeliveryDate, receivedUnits.
    ``receipts`` rows: store_id, shipmentId, gtin, transactionTime, changedUnits (Receipt only).
    """

    wm: dict[str, dict[str, Any]] = {}
    stores: set[str] = set()
    for r in shipments:
        sh = str(r.get("shipmentId") or "")
        if not sh:
            continue
        stores.add(str(r.get("store_id") or ""))
        wm[sh] = {
            "store_id": str(r.get("store_id") or ""),
            "status": r.get("status") or "",
            "actualDelivery": _d(r.get("actualDeliveryDate")),
            "receivedUnits": _num(r.get("receivedUnits")),
            "firstReceipt": "",
            "lastReceipt": "",
            "receiptUnits": 0,
        }
    agg: dict[str, dict[str, Any]] = {}
    for r in receipts:
        sh = str(r.get("shipmentId") or "")
        if not sh:
            continue
        a = agg.setdefault(sh, {"first": "", "last": "", "units": 0, "by": Counter(), "sid": ""})
        a["sid"] = str(r.get("store_id") or "")
        t = str(r.get("transactionTime") or "")[:19].replace("T", " ")
        if t:
            a["first"] = min(a["first"] or t, t)
            a["last"] = max(a["last"], t)
        a["units"] += _num(r.get("changedUnits"))
    for sh, a in agg.items():
        w = wm.setdefault(
            sh,
            {
                "store_id": a["sid"],
                "status": "",
                "actualDelivery": "",
                "receivedUnits": 0,
            },
        )
        w["firstReceipt"] = a["first"][:10]
        w["lastReceipt"] = a["last"][:10]
        w["receiptUnits"] = a["units"]
    for w in wm.values():
        if (
            w.get("actualDelivery")
            and w["actualDelivery"] > today_s
            and w.get("status") == "AWAITING_DELIVERY"
        ):
            # Walmart writes the appointment date into actualDeliveryDate while awaiting.
            w["actualDelivery"] = ""
    return wm, stores
