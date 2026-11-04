"""货代看板 (8088 ``众壹接口面板`` ``zy_panel``, renamed by Rocky 2026-11-03): one row per
carrier order from the validated 众壹 files, linked to its SP, plus the SPs whose tracking
number has no order and the 众壹 SPs without a tracking number. Pure functions, no I/O.

Pull / API-call statistics of the 8088 panel came from the puller's request log; the new
system only reads validated files, so they are not shown.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any, Final

STALE_DAYS: Final = 7
SIGNED: Final = "已签收"


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def zy_provider_ids(providers: Mapping[str, str]) -> set[str]:
    return {pid for pid, name in providers.items() if "众壹" in (name or "")}


def carrier_orders(
    sps: Sequence[Mapping[str, Any]],
    orders: Iterable[Mapping[str, Any]],
    tracks: Iterable[Mapping[str, Any]],
    stores: Mapping[str, str],
    today: date,
    providers: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """8088 ``zy_panel.orders``: first summary row per order number, latest track first.

    物流商 (Rocky 2026-11-04): the linked SP's provider; an order not linked to an SP keeps
    the provider of its source file (众壹 is the only carrier with validated files today).
    """

    providers = providers or {}
    src_ids = sorted(zy_provider_ids(providers))
    src_id = src_ids[0] if src_ids else ""
    src_name = providers.get(src_id, "众壹物流") if src_id else "众壹物流"

    by_tn: dict[str, Mapping[str, Any]] = {}
    for s in sps:
        for t in s.get("tracking") or []:
            by_tn[t] = s
    cargo_to_sp = {c["code"]: s for s in sps for c in s.get("cargos") or []}
    summary: dict[str, Mapping[str, Any]] = {}
    for r in orders:
        summary.setdefault(str(r.get("number") or ""), r)
    summary.pop("", None)
    trs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for t in tracks:
        trs[str(t.get("orderNumber") or "")].append(t)
    out: list[dict[str, Any]] = []
    for number, r in summary.items():
        s = (
            by_tn.get(number)
            or cargo_to_sp.get(str(r.get("customerNumber") or ""))
            or by_tn.get(str(r.get("shipping_code") or ""))
        )
        ev = sorted(trs[number], key=lambda x: str(x.get("trackTime") or ""), reverse=True)
        latest = ev[0] if ev else {}
        last = str(latest.get("trackTime") or "")
        stale = (today - date.fromisoformat(last[:10])).days if last[:10] else None
        status = r.get("status") or ""
        out.append(
            {
                "number": number,
                "customerNumber": r.get("customerNumber") or "",
                "status": status,
                "provider_id": (s.get("provider_id") or "") if s else src_id,
                "provider": (
                    providers.get(s.get("provider_id") or "", s.get("provider_id") or "")
                    if s
                    else src_name
                ),
                "serviceNumber": r.get("serviceNumber") or "",
                "kg": _f(r.get("totalWeightKg")),
                "weight": _f(r.get("weight")),
                "cbm": _f(r.get("volume")),
                "sp": s["code"] if s else "",
                "sp_status": s.get("status", "") if s else "",
                "sp_boxes": s.get("boxes", 0) if s else 0,
                "fc": s.get("fc", "") if s else "",
                "region": s.get("region", "") if s else "",
                "store_id": s.get("store_id", "") if s else "",
                "store": stores.get(s.get("store_id", ""), s.get("store_id", "")) if s else "",
                "trackCn": latest.get("name") or "",
                "trackEn": latest.get("enName") or "",
                "lastTrack": last[:16],
                "nTracks": len(ev),
                "staleDays": stale,
                "stale": stale is not None and stale >= STALE_DAYS and status != SIGNED,
                "tracks": [
                    {
                        "t": str(e.get("trackTime") or "")[:16],
                        "cn": e.get("name") or "",
                        "en": e.get("enName") or "",
                        "bl": e.get("ladingNumber") or "",
                        "lat": e.get("latitude") or "",
                        "lng": e.get("longitude") or "",
                    }
                    for e in ev
                ],
            }
        )
    return out


def missing_orders(
    sps: Sequence[Mapping[str, Any]],
    order_numbers: set[str],
    zy_ids: set[str],
    stores: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """(查不到, 无运单号, 应查运单数, 众壹发货单数) as 8088 ``not_found`` / ``no_tracking``."""

    zy_sps = [
        s
        for s in sps
        if s.get("provider_id") in zy_ids
        or any(str(t).startswith("ZY") for t in s.get("tracking") or [])
    ]
    by_tn = {t: s for s in sps for t in s.get("tracking") or []}
    queried = {t for s in zy_sps for t in s.get("tracking") or [] if str(t).startswith("ZY")}
    not_found = [
        {
            "kind": "查不到",
            "tracking": t,
            "sp": by_tn[t]["code"],
            "sp_status": by_tn[t].get("status", ""),
            "store": stores.get(by_tn[t].get("store_id", ""), ""),
            "why": "已校验的众壹文件里没有这张运单",
        }
        for t in sorted(queried - order_numbers)
        if t in by_tn
    ]
    no_tracking = [
        {
            "kind": "无运单号",
            "tracking": "",
            "sp": s["code"],
            "sp_status": s.get("status", ""),
            "store": stores.get(s.get("store_id", ""), ""),
            "created": s.get("created", ""),
            "why": "领星发货单未填 tracking_number",
        }
        for s in zy_sps
        if not s.get("tracking") and s.get("status") != "已作废"
    ]
    return not_found, no_tracking, len(queried), len(zy_sps)


def sort_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stale first, then latest track first (8088 TabZy order)."""

    return sorted(orders, key=lambda o: (not o["stale"], _neg(o["lastTrack"]), o["number"]))


def _neg(text: str) -> tuple[int, ...]:
    return tuple(-ord(ch) for ch in text) + (0,)


def status_counts(orders: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(Counter(o["status"] for o in orders).most_common())


def provider_counts(orders: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """物流商 filter options: provider id, name and order count, most orders first."""

    counts: Counter[tuple[str, str]] = Counter(
        (o.get("provider_id") or "", o.get("provider") or "") for o in orders
    )
    return [
        {"value": pid, "label": name or pid or "未知物流商", "count": n}
        for (pid, name), n in sorted(counts.items(), key=lambda x: (-x[1], x[0][1], x[0][0]))
    ]
