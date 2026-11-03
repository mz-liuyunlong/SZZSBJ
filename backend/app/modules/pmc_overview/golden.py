"""Load 8088 golden snapshots (exported locally from the DEMO page) and compare.

Real data never enters the repository; the snapshot path is passed at runtime.
"""

from __future__ import annotations

from typing import Any

from app.modules.pmc_overview.calculations import (
    DomesticBatchAge,
    ItemInput,
    ItemResult,
    RecentPlan,
    SupplyBatch,
    compute_all,
)
from app.modules.pmc_overview.rules import params_from_demo


def item_from_dict(d: dict[str, Any]) -> ItemInput:
    return ItemInput(
        item_id=str(d["item_id"]),
        sku=d["sku"],
        daily=float(d["daily"]),
        n30=int(d["n30"]),
        oos_days=d["oos_days"],
        no_stock_90=bool(d["no_stock_90"]),
        tail_stock=bool(d["tail_stock"]),
        max_start=int(d["max_start"] or 0),
        supply=int(d["supply"]),
        wm_available=int(d["wm_available"] or 0),
        sellout=d["sellout"],
        gap_days=d["gap_days"],
        resume=d["resume"],
        next_date=d["next_date"],
        lead_total=float(d["lead_total"]),
        lead_avg=d["lead_avg"],
        suggest=int(d["suggest"]),
        suggest_raw=int(d["suggest_raw"]),
        cap_on=bool(d["cap_on"]),
        capped=bool(d["capped"]),
        box=int(d.get("box") or 0),
        box_missing_after_ship=bool(d.get("box_missing_after_ship")),
        listing=d.get("listing") or "",
        tags=tuple(d.get("tags") or ()),
        plans_recent=tuple(RecentPlan(**p) for p in d.get("plans_recent") or ()),
        draft_id=d.get("draft_id") or "",
        overseas_sku=int(d.get("overseas_sku") or 0),
        batches=tuple(
            SupplyBatch(**{k: v for k, v in b.items() if k != "lock"})
            for b in d.get("batches") or ()
        ),
        dom_rows=tuple(DomesticBatchAge(**r) for r in d.get("dom_rows") or ()),
    )


def _actual(r: ItemResult) -> dict[str, Any]:
    return {
        "issues": [[i.label, i.level] for i in r.issues],
        "main": r.main,
        "cats": r.cats,
        "over": r.over,
        "cover": r.cover,
        "stale": r.stale,
        "risk": r.risk,
        "oos": r.oos,
        "overseas_alloc": r.overseas_alloc,
        "purchase": r.purchase,
        "boxed": r.boxed,
        "is_draft": r.is_draft,
        "draft": r.draft_text,
    }


DEMO_KPI_MAP = {
    "items": "items",
    "listingBad": "listing_bad",
    "oos": "oos",
    "risk": "risk",
    "over1": "over1",
    "over2": "over2",
    "stale": "stale",
    "sc": "supply_chain",
    "exec": "execution",
    "noStock90": "no_stock_90",
    "lowDays": "low_days",
    "overseas": "overseas",
    "drafts": "drafts",
    "normal": "normal",
    "lowSupply": "low_supply",
    "overdue": "overdue",
    "box": "box_missing",
}


def compare_snapshot(snap: dict[str, Any], draft_mode: str = "demo_8088") -> dict[str, Any]:
    """Return {'kpi_diff': {...}, 'item_diffs': [...]}; empty = identical to 8088."""
    items = [item_from_dict(x["input"]) for x in snap["items"]]
    results, kpi = compute_all(items, params_from_demo(snap["params"]), snap["today"], draft_mode)  # type: ignore[arg-type]
    kpi_diff = {
        k: {"demo": snap["kpi"][k], "ours": kpi[v]}
        for k, v in DEMO_KPI_MAP.items()
        if snap["kpi"].get(k) != kpi[v]
    }
    item_diffs = []
    for x, r in zip(snap["items"], results, strict=True):
        act = _actual(r)
        bad = {
            k: {"demo": x["expect"][k], "ours": act[k]} for k in act if x["expect"].get(k) != act[k]
        }
        if bad:
            item_diffs.append({"item_id": r.item_id, "diff": bad})
    return {"kpi_diff": kpi_diff, "item_diffs": item_diffs}
