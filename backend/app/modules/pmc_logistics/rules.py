"""8088 物流看板规则 (pmc-logistics ``app-a.jsx`` ``enrich``): per SP shipping list, stage,
arrival / sellable chain, contract time limit and alerts. Pure functions, no I/O.

Inputs mirror the 8088 data shape so the port can be checked line by line:

* ``sp``: code, status, provider_id, channel_id, channel, method, region, fc, tracking,
  gw, cost {transport, other}, t {delivery, actual_delivery, sail, expected_arrival,
  arrival}, cargos [{code, status, store_id, to_receive, to_closed, declare, received}].
* ``track``: carrier order for the SP: nodes {etd, atd, eta, ata, delivered, opc,
  est_delivery} and totalWeightKg, or ``None``.
* ``wm``: Walmart facts by shipment id: status, actualDelivery, firstReceipt, lastReceipt,
  receiptUnits, receivedUnits.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Final

REGIONS: Final = ("美西", "美中", "美东")
REGION_CYCLE: Final = {"美西": 7, "美中": 10, "美东": 12}
REGION_STAGE: Final = {
    "美西": {"toSail": 7, "voyage": 16},
    "美中": {"toSail": 6, "voyage": 20},
    "美东": {"toSail": 8, "voyage": 40},
}
CONTRACT_DAYS: Final = {"美西": 35, "美中": 42, "美东": 48}
DONE_STAGES: Final = frozenset({"物流签收", "Walmart 收货中", "Walmart 完成", "已作废"})
STAGES: Final = (
    "待发货",
    "已发货",
    "已开船",
    "已到港",
    "派送中",
    "物流签收",
    "Walmart 收货中",
    "Walmart 完成",
    "已作废",
)


@dataclass(slots=True)
class LogisticsRules:
    remind_before: int = 3
    delivered_not_signed: int = 2
    receive_diff_buffer: int = 7
    cost_missing_after: int = 3
    time_missing_after: int = 2
    wm_receive_buffer: int = 10
    penalty_per_kg_day: float = 0.5
    region_total: dict[str, int] = field(
        default_factory=lambda: {"美西": 50, "美中": 60, "美东": 80}
    )
    cycle: dict[str, dict[str, Any]] = field(default_factory=dict)
    contract: list[dict[str, Any]] = field(default_factory=list)


def channel_regions(name: str | None) -> list[str]:
    n = name or ""
    if "COSCO、EMC" in n:
        return ["美西"]
    if "美东" in n or "萨凡纳" in n or "NY" in n:
        return ["美东"]
    if "芝加哥" in n or "休斯顿" in n or "HOU" in n:
        return ["美中"]
    if "洛杉矶" in n or "LALB" in n:
        return ["美西"]
    return list(REGIONS)


def cycle_days(name: str | None) -> tuple[int | None, str]:
    n = name or ""
    if "美东直航" in n:
        return 12, "real"
    if "美东限时达" in n:
        return 15, "real"
    if "芝加哥" in n:
        return 18, "real"
    if "休斯顿" in n or "萨凡纳专线" in n:
        return 10, "real"
    regions = channel_regions(n)
    if len(regions) == 1 and regions[0] == "美西":
        return 7, "real"
    return None, "region"


def stage_days(name: str | None) -> dict[str, Any] | None:
    n = name or ""
    if "COSCO、EMC" in n:
        return {"toSail": 7, "voyage": 16}
    if "美东限时达" in n:
        return {"toSail": 6, "voyage": 13}
    if "美东直航" in n:
        return {"toSail": 12, "voyage": 44}
    if "芝加哥" in n:
        return {"toSail": 5, "voyage": 13}
    if "休斯顿" in n:
        return {"toSail": 6, "voyage": 32}
    return None


def default_rules(sps: Iterable[Mapping[str, Any]]) -> LogisticsRules:
    """8088 ``RULES_INIT``: channel cycles and contract days seeded from the SPs present."""

    rules = LogisticsRules()
    seen: set[str] = set()
    for sp in sps:
        if not sp.get("provider_id"):
            continue
        cid = sp.get("channel_id") or ""
        if cid not in rules.cycle:
            days, src = cycle_days(sp.get("channel"))
            stage = stage_days(sp.get("channel"))
            rules.cycle[cid] = {
                "days": days,
                "src": src,
                "toSail": stage["toSail"] if stage else None,
                "voyage": stage["voyage"] if stage else None,
            }
        for region in channel_regions(sp.get("channel")):
            key = f"{sp['provider_id']}|{cid}|{region}"
            if key in seen:
                continue
            seen.add(key)
            rules.contract.append(
                {
                    "provider_id": sp["provider_id"],
                    "channel_id": cid,
                    "region": region,
                    "days": CONTRACT_DAYS[region],
                    "remind": 3,
                }
            )
    return rules


def _d(value: str | None) -> date | None:
    text = (value or "")[:10]
    try:
        return date.fromisoformat(text) if len(text) == 10 else None
    except ValueError:
        return None


def _days(a: str, b: str) -> int | None:
    da, db = _d(a), _d(b)
    return (db - da).days if da and db else None


def _add(day: str, n: int) -> str:
    parsed = _d(day)
    return (parsed + timedelta(days=n)).isoformat() if parsed else ""


def _min(values: Iterable[str]) -> str:
    present = sorted(v for v in values if v)
    return present[0] if present else ""


def _max(values: Iterable[str]) -> str:
    present = sorted(v for v in values if v)
    return present[-1] if present else ""


def _js_round2(value: float) -> float:
    # Math.round(x*100)/100 (half up for positives).
    return math.floor(value * 100 + 0.5) / 100


def _fmt_num(value: float) -> str:
    # JS template literal number formatting for the values used in alert text.
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def enrich_sp(
    sp: Mapping[str, Any],
    track: Mapping[str, Any] | None,
    wm_facts: Mapping[str, Mapping[str, Any]],
    wm_stores: set[str],
    rules: LogisticsRules,
    today: date,
    *,
    wm_day: str = "",
) -> dict[str, Any]:
    today_s = today.isoformat()
    nd = (track or {}).get("nodes") or {}
    t = sp.get("t") or {}
    cg: Sequence[Mapping[str, Any]] = sp.get("cargos") or []
    region = sp.get("region") or "待定"
    all_closed = (
        len(cg) > 0
        and all(c.get("status") in ("CLOSED", "CANCELLED") for c in cg)
        and any(c.get("status") == "CLOSED" for c in cg)
    )
    any_receiving = any(c.get("status") == "RECEIVING_IN_PROGRESS" for c in cg)
    wm_first_receive = _min(c.get("to_receive") or "" for c in cg)
    wm_closed = _max(c.get("to_closed") or "" for c in cg)
    sail = t.get("sail") or ""
    etd = nd.get("etd") or (sail if sail and sail > today_s else "")
    atd = nd.get("atd") or (sail if sail and sail <= today_s else "")
    eta = t.get("expected_arrival") or nd.get("eta") or ""
    ata = nd.get("ata") or ""
    delivered = nd.get("delivered") or ""
    pickup = nd.get("opc") or t.get("actual_delivery") or t.get("delivery") or ""
    cr = rules.cycle.get(sp.get("channel_id") or "") or {}
    cyc = cr.get("days") if cr.get("days") is not None else REGION_CYCLE.get(region)
    cyc_src = cr.get("src") if cr.get("days") is not None else "region"
    region_stage = REGION_STAGE.get(region) or {}
    voyage = cr.get("voyage") if cr.get("voyage") is not None else region_stage.get("voyage")
    plan, plan_src = "", ""
    if nd.get("est_delivery"):
        plan, plan_src = nd["est_delivery"], "carrier_est"
    elif ata and cyc is not None:
        plan, plan_src = _add(ata, cyc), "ata+cycle"
    elif atd and voyage is not None and cyc is not None:
        plan, plan_src = _add(atd, voyage + cyc), "atd+voyage+cycle"
    elif eta and cyc is not None:
        plan, plan_src = _add(eta, cyc), "eta+cycle"
    elif t.get("arrival"):
        plan, plan_src = t["arrival"], "lx_arrival"
    elif (t.get("delivery") or t.get("actual_delivery")) and region in rules.region_total:
        plan = _add(t.get("delivery") or t.get("actual_delivery"), rules.region_total[region])
        plan_src = "region_total"
    wm = [dict(wm_facts[c["code"]], code=c["code"]) for c in cg if c.get("code") in wm_facts]
    wm_covered = len(cg) > 0 and all(c.get("store_id") in wm_stores for c in cg)
    wm_last_receipt = _max(x.get("lastReceipt") or "" for x in wm)
    wm_receipt_done = len(wm) > 0 and all(
        x.get("lastReceipt")
        and (
            x.get("status") == "CLOSED"
            or (x.get("receivedUnits") and (x.get("receiptUnits") or 0) >= x["receivedUnits"])
        )
        for x in wm
    )
    wm_receipt_start = _min(x.get("firstReceipt") or "" for x in wm)
    wm_actual_delivery = _min(x.get("actualDelivery") or "" for x in wm)
    channel = sp.get("channel") or ""
    region_ok = region in channel_regions(channel)
    actual = _min([delivered, wm_actual_delivery])
    actual_src = "" if not actual else ("carrier" if actual == delivered else "wm_sign")
    arrival, arrival_src = actual, ("real" if actual else "")
    if not arrival:
        arrival = plan
        arrival_src = "calc" if plan_src == "region_total" else "plan"
    if sp.get("status") == "已作废":
        stage = "已作废"
    elif sp.get("status") != "已发货":
        stage = "待发货"
    elif all_closed or (wm and all(x.get("status") == "CLOSED" for x in wm)):
        stage = "Walmart 完成"
    elif (
        any_receiving
        or wm_first_receive
        or wm_receipt_start
        or any(x.get("status") == "RECEIVING_IN_PROGRESS" for x in wm)
    ):
        stage = "Walmart 收货中"
    elif delivered:
        stage = "物流签收"
    elif ata:
        stage = "派送中" if (_days(ata, today_s) or 0) >= 4 else "已到港"
    elif atd:
        stage = "已开船"
    else:
        stage = "已发货"
    done = stage in DONE_STAGES
    ct = next(
        (
            c
            for c in rules.contract
            if c["provider_id"] == sp.get("provider_id")
            and c["channel_id"] == sp.get("channel_id")
            and c["region"] == region
        ),
        None,
    )
    deadline = _add(pickup, ct["days"] + 1) if ct and pickup else ""
    signed_at = (
        delivered
        or wm_actual_delivery
        or wm_receipt_start
        or wm_first_receive
        or (wm_closed if all_closed else "")
        or ""
    )
    remain = None
    if deadline:
        remain = -(_days(deadline, signed_at) or 0) if signed_at else _days(today_s, deadline)
    overdue = bool(deadline) and not done and not signed_at and remain is not None and remain < 0
    soon = (
        bool(deadline)
        and not done
        and not signed_at
        and remain is not None
        and 0 <= remain <= (ct["remind"] if ct else rules.remind_before)
    )
    used_days = None
    if pickup:
        used_days = (
            _days(pickup, signed_at) if signed_at else (None if done else _days(pickup, today_s))
        )
    overdue_days = max(0, _days(deadline, signed_at or today_s) or 0) if deadline else 0
    weight = (track or {}).get("totalWeightKg") or sp.get("gw") or 0
    penalty = (
        _js_round2(overdue_days * rules.penalty_per_kg_day * weight) if overdue_days > 0 else 0
    )
    sellable = wm_receipt_start or (_add(arrival, rules.wm_receive_buffer) if arrival else "")
    wm_sign = wm_actual_delivery or wm_receipt_start or ""
    sign_gap = _days(delivered, wm_sign) if delivered and wm_sign else None
    if not delivered:
        sign_check = "none"
    elif wm_sign:
        sign_check = "ok" if (sign_gap or 0) <= rules.delivered_not_signed else "late"
    elif not wm_covered:
        sign_check = "nodata"
    elif all_closed:
        sign_check = "closed"
    else:
        sign_check = (
            "overdue"
            if (_days(delivered, today_s) or 0) > rules.delivered_not_signed
            else "waiting"
        )
    age = _days(t.get("delivery") or "", today_s) if t.get("delivery") else 0
    age = age or 0
    missing: list[str] = []
    cost = sp.get("cost") or {}
    if sp.get("status") == "已发货":
        if (cost.get("transport") or 0) == 0 and age >= rules.cost_missing_after:
            missing.append("实际费用未录入")
        if not etd and not atd and age >= rules.time_missing_after:
            missing.append("预计开船缺失")
        if not eta and age >= rules.time_missing_after:
            missing.append("预计到港缺失")
        if not sp.get("tracking"):
            missing.append("运单号缺失")
        if not cg:
            missing.append("未关联 WFS 货件")
        if not ct:
            missing.append("无合同时效")
    ex: list[dict[str, Any]] = []
    fc = sp.get("fc") or ""
    if not region_ok:
        ex.append(
            {
                "type": "渠道与目的地区不符",
                "sev": "mid",
                "desc": (
                    f"渠道「{channel}」只去 {'/'.join(channel_regions(channel))}，"
                    f"本单目的仓 {fc} 归 {region}（FC 地区映射或渠道规则待确认）"
                ),
                "since": t.get("delivery") or today_s,
            }
        )
    wfs_received = sum(int(c.get("received") or 0) for c in cg)
    if delivered and cg and wfs_received == 0:
        n = _days(delivered, today_s)
        seen = wm_actual_delivery or wm_receipt_start or wm_first_receive
        desc = (
            f"物流商 {delivered} 派送完成（签收完成），{n} 天后领星 WFS 关联货件收货量合计仍为 0"
            "（领星口径：wfs_cargos.cargo_good_list.received_num；阈值 "
            f"{rules.delivered_not_signed} 天）"
        )
        if seen:
            desc += (
                "；Walmart 侧"
                + (f" 已签收 {wm_actual_delivery}" if wm_actual_delivery else "")
                + (
                    f" 已开始收货（首次 Receipt {wm_receipt_start or wm_first_receive}）"
                    if wm_receipt_start or wm_first_receive
                    else ""
                )
                + " → 多半是领星收货数未同步，不是物流问题"
            )
        elif wm_covered:
            desc += "；Walmart 侧也无签收 / 无 Receipt——需向物流商核实是否真的送达"
        else:
            desc += "；Walmart 数据未覆盖该店铺——需向物流商核实是否真的送达"
        ex.append(
            {
                "type": "物流已签收 WFS 未收货",
                "sev": "mid" if seen else "high",
                "desc": desc,
                "since": _add(delivered, rules.delivered_not_signed),
            }
        )
    elif delivered and not cg:
        ex.append(
            {
                "type": "未关联 WFS 货件",
                "sev": "low",
                "desc": (
                    f"物流商 {delivered} 已签收，但本单未关联到 WFS 货件，无法判定 WFS 收货情况"
                    "——数据待核查（不计入「物流已签收 WFS 未收货」）"
                ),
                "since": delivered,
            }
        )
    if sign_check == "overdue":
        ex.append(
            {
                "type": "物流已签收 Walmart 未签收",
                "sev": "high",
                "desc": (
                    f"物流商 {delivered} 派送完成，{_days(delivered, today_s)} 天后"
                    " Walmart 仍无签收"
                    f" actualDeliveryDate 也无 Receipt（阈值 {rules.delivered_not_signed} 天；"
                    f"Walmart 批次 {wm_day}）——向物流商核实是否真的送达 / "
                    "到 Seller Center 看货件"
                ),
                "since": _add(delivered, rules.delivered_not_signed),
            }
        )
    if sign_check == "late":
        ex.append(
            {
                "type": "Walmart 签收滞后于物流到货",
                "sev": "mid",
                "desc": (
                    f"物流商 {delivered} 派送完成，Walmart {wm_sign} 才签收，相差 {sign_gap} 天"
                    f"（阈值 {rules.delivered_not_signed} 天）"
                ),
                "since": wm_sign,
            }
        )
    if wm_first_receive and track and not delivered:
        ex.append(
            {
                "type": "Walmart 已收货 物流未显示派送",
                "sev": "low",
                "desc": (
                    f'Walmart {wm_first_receive} 已开始收货，物流商轨迹仍未到"签收完成"'
                    "——物流数据延迟或质量问题"
                ),
                "since": wm_first_receive,
            }
        )
    for c in cg:
        if c.get("status") != "CLOSED" or c.get("declare") == c.get("received"):
            continue
        n = _days(c["to_closed"], today_s) if c.get("to_closed") else 0
        n = n or 0
        diff = int(c.get("received") or 0) - int(c.get("declare") or 0)
        over = n >= rules.receive_diff_buffer
        ex.append(
            {
                "type": "收货差异（超缓冲期）" if over else "收货差异（观察期）",
                "sev": ("high" if abs(diff) >= 20 else "mid") if over else "low",
                "desc": (
                    f"货件 {c['code']} Closed：实收 {c.get('received')} − "
                    f"申报 {c.get('declare')} = "
                    f"{'+' if diff > 0 else ''}{diff}，Closed 已 {n} 天"
                    f"（缓冲 {rules.receive_diff_buffer} 天）"
                ),
                "since": c.get("to_closed") or today_s,
                "cargo": c["code"],
            }
        )
    rate = _fmt_num(rules.penalty_per_kg_day)
    if overdue and ct:
        claim = (
            f"，按合同可索赔 ¥{_fmt_num(penalty)}（{overdue_days} 天 × {rate} 元/KG × "
            f"计费重 {_fmt_num(weight)} KG）"
            if penalty
            else ""
        )
        ex.append(
            {
                "type": "已超合同时效",
                "sev": "high",
                "desc": (
                    f"合同时效 {ct['days']} 天（提货 {pickup} 次日起），截止 {deadline}，"
                    f"已超 {-(remain or 0)} 天仍未签收{claim}"
                ),
                "since": deadline,
            }
        )
    elif signed_at and overdue_days > 0 and ct:
        ex.append(
            {
                "type": "签收已超时效（可索赔）",
                "sev": "mid",
                "desc": (
                    f"合同时效 {ct['days']} 天，截止 {deadline}，实际签收 {signed_at} 超 "
                    f"{overdue_days} 天" + (f"，可索赔 ¥{_fmt_num(penalty)}" if penalty else "")
                ),
                "since": signed_at,
            }
        )
    elif soon and ct:
        ex.append(
            {
                "type": "即将超时",
                "sev": "mid",
                "desc": f"合同时效 {ct['days']} 天，截止 {deadline}，还剩 {remain} 天",
                "since": today_s,
            }
        )
    for m in missing:
        ex.append(
            {
                "type": m,
                "sev": "low",
                "desc": f"{m}（发货 {t.get('delivery') or '—'}，已 {age} 天）",
                "since": today_s,
                "missing": True,
            }
        )
    return {
        "code": sp.get("code"),
        "stage": stage,
        "done": done,
        "etd": etd,
        "atd": atd,
        "eta": eta,
        "ata": ata,
        "pickup": pickup,
        "arrivalPlan": plan,
        "arrivalPlanSrc": plan_src,
        "arrivalActual": actual,
        "arrivalActualSrc": actual_src,
        "cyc": cyc,
        "cycSrc": cyc_src,
        "wmLastReceipt": wm_last_receipt,
        "wmReceiptDone": wm_receipt_done,
        "sellableSrc": "real" if wm_receipt_start else "plan",
        "deliveredCarrier": delivered,
        "wmFirstReceive": wm_first_receive,
        "wmClosed": wm_closed,
        "wmReceiptStart": wm_receipt_start,
        "wmActualDelivery": wm_actual_delivery,
        "wmSign": wm_sign,
        "signGap": sign_gap,
        "signCheck": sign_check,
        "wmCovered": wm_covered,
        "chargeWeight": (track or {}).get("totalWeightKg") or None,
        "arrivalDate": arrival,
        "arrivalSrc": arrival_src,
        "sellableDate": sellable,
        "deadline": deadline,
        "remain": remain,
        "overdue": overdue,
        "soon": soon,
        "usedDays": used_days,
        "overdueDays": overdue_days,
        "penalty": penalty,
        "regionOk": region_ok,
        "age": age,
        "missing": missing,
        "declared": sum(int(c.get("declare") or 0) for c in cg),
        "received": wfs_received,
        "daysToArrival": _days(today_s, arrival) if arrival else None,
        "daysToSellable": _days(today_s, sellable) if sellable else None,
        "ct": ct["days"] if ct else None,
        "ex": ex,
    }
