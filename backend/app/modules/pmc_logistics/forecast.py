"""到货预测 (8088 ``app-b.jsx`` ``cargoArrivals`` + ``TabForecast`` rows): shipped, not yet
closed cargo × SKU lines, bucketed by the expected sellable date. Pure functions, no I/O.

Rules (Rocky 2026-09-25, same as the ops data sheet):

* a cargo × SKU with ≥1 unit shelved (Walmart Receipt for that shipment and GTIN) is
  「已到·收货中」, sellable date = first Receipt;
* otherwise sellable date = arrival date + ``wm_receive_buffer`` days, where the arrival date
  is the earliest actual (carrier delivered / Walmart signed) or else the latest plan;
* signed = Walmart inbound-item ``receivedQty`` for the GTIN, else Lingxing ``received_num``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any, Final

BUCKETS: Final = (
    ("bOver", "已过预计可售日未上架", -99999, -1),
    ("b15", "15 天内可售", 0, 15),
    ("b30", "15–30 天可售", 16, 30),
    ("b60", "30–60 天可售", 31, 60),
    ("b60p", "超过 60 天可售", 61, 99999),
)
NONE_BUCKET: Final = ("bNone", "无预计日期")
ARRIVED: Final = "已到·收货中"
SUM_KEYS: Final = (
    "total",
    "bOver",
    "b15",
    "b30",
    "b60",
    "b60p",
    "bNone",
    "signedNP",
    "aShip",
    "aSign",
    "aShelf",
    "anom",
)


def cargo_arrivals(
    rows: Sequence[Mapping[str, Any]], wm: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Arrival date per WFS cargo across its shipped SPs: earliest actual, else latest plan."""

    acc: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for s in rows:
        if s.get("status") != "已发货":
            continue
        for c in s.get("cargos") or []:
            a = acc.setdefault(c["code"], {"acts": [], "plans": []})
            if s.get("arrivalActual"):
                a["acts"].append((s["arrivalActual"], s.get("arrivalActualSrc") or ""))
            if s.get("arrivalPlan"):
                a["plans"].append((s["arrivalPlan"], s.get("arrivalPlanSrc") or ""))
            w = wm.get(c["code"])
            if w and w.get("actualDelivery"):
                a["acts"].append((w["actualDelivery"], "wm_sign"))
    out: dict[str, dict[str, Any]] = {}
    for code, a in acc.items():
        if a["acts"]:
            day, src = min(a["acts"], key=lambda x: x[0])
            out[code] = {"date": day, "src": src, "real": True}
        elif a["plans"]:
            day, src = max(a["plans"], key=lambda x: x[0])
            out[code] = {"date": day, "src": src, "real": False}
    return out


def _add(day: str, n: int) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=n)).isoformat()


def _bucket(days: int | None) -> tuple[str, str]:
    if days is None:
        return NONE_BUCKET
    for key, label, lo, hi in BUCKETS:
        if lo <= days <= hi:
            return key, label
    return NONE_BUCKET


def forecast_rows(
    rows: Sequence[Mapping[str, Any]],
    wm: Mapping[str, Mapping[str, Any]],
    today: date,
    wm_receive_buffer: int,
    *,
    item_ids: Mapping[tuple[str, str], str] | None = None,
    owners: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Product rows (store × MSKU) with per cargo × SKU lines, in first-seen order.

    ``rows`` are enriched SPs (Lingxing SP fields + 8088 ``enrich`` fields).
    """

    item_ids = item_ids or {}
    owners = owners or {}
    arrivals = cargo_arrivals(rows, wm)
    out: dict[str, dict[str, Any]] = {}
    for s in rows:
        if s.get("status") != "已发货":
            continue
        cargos = {c["code"]: c for c in s.get("cargos") or []}
        for g in s.get("goods") or []:
            cg = cargos.get(g.get("cargo") or "")
            if cg and cg.get("status") in ("CLOSED", "CANCELLED"):
                continue  # 货件已关闭 = 收货完成，不再计
            qty = g.get("qty") or 0
            if not qty > 0:
                continue
            key = f"{g['store_id']}|{g['msku']}"
            r = out.get(key)
            if r is None:
                r = out[key] = {
                    "key": key,
                    "store": g.get("store", ""),
                    "store_id": g["store_id"],
                    "sku": g.get("sku", ""),
                    "msku": g["msku"],
                    "gtin": g.get("gtin", ""),
                    "name": g.get("name", ""),
                    "item_id": item_ids.get((g["store_id"], g["msku"]), ""),
                    "owner": "、".join(owners.get(g.get("sku", ""), ())),
                    **{k: 0 for k in SUM_KEYS},
                    "lines": [],
                    "nextArr": "",
                    "nextSell": "",
                }
            ci = (
                next((x for x in cg.get("items") or [] if x.get("msku") == g["msku"]), None)
                if cg
                else None
            )
            wmf = wm.get(cg["code"]) if cg else None
            gtin = g.get("gtin", "")
            recv = (wmf or {}).get("itemsRecv") or {}
            signed = recv[gtin] if gtin in recv else ((ci or {}).get("received") or 0)
            shelved = ((wmf or {}).get("byGtin") or {}).get(gtin, 0) or 0
            base = {
                "code": s["code"],
                "cargo": g.get("cargo", ""),
                "stage": s.get("stage", ""),
                "fc": s.get("fc", ""),
                "region": s.get("region", ""),
                "ship": qty,
                "sign": signed,
                "shelf": shelved,
            }
            if shelved > 0:  # ≥1 件上架 → 已到·收货中（Rocky 2026-09-25）
                r["aShip"] += qty
                r["aSign"] += signed
                r["aShelf"] += shelved
                if signed == 0:
                    r["anom"] += 1
                r["lines"].append(
                    {
                        **base,
                        "bucket": ARRIVED,
                        "arr": "",
                        "arrSrc": "",
                        "arrReal": False,
                        "sell": (wmf or {}).get("firstReceipt") or "",
                        "sellReal": True,
                        "days": None,
                    }
                )
                continue
            a = arrivals.get(g.get("cargo") or "")
            if a is None and s.get("arrivalDate"):
                a = {
                    "date": s["arrivalDate"],
                    "src": s.get("arrivalActualSrc")
                    if s.get("arrivalActual")
                    else s.get("arrivalPlanSrc"),
                    "real": bool(s.get("arrivalActual")),
                }
            sell = _add(a["date"], wm_receive_buffer) if a else ""
            days = (date.fromisoformat(sell) - today).days if sell else None
            bkey, blabel = _bucket(days)
            r["total"] += qty
            r[bkey] += qty
            if signed > 0:
                r["signedNP"] += signed
            if a and (not r["nextArr"] or a["date"] < r["nextArr"]):
                r["nextArr"] = a["date"]
            if sell and (not r["nextSell"] or sell < r["nextSell"]):
                r["nextSell"] = sell
            r["lines"].append(
                {
                    **base,
                    "bucket": blabel,
                    "arr": a["date"] if a else "",
                    "arrSrc": (a["src"] or "") if a else "",
                    "arrReal": bool(a and a["real"]),
                    "sell": sell,
                    "sellReal": False,
                    "days": days,
                }
            )
    return list(out.values())


def forecast_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    summary = {k: sum(r[k] for r in rows) for k in SUM_KEYS}
    summary["products"] = sum(1 for r in rows if r["total"] > 0)
    summary["rows"] = len(rows)
    return summary
