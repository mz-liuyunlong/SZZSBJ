"""Filtering / paging / shaping on top of :func:`snapshot.load_board` (no DB, no IO besides it)."""

from __future__ import annotations

from typing import Any

from app.modules.pmc_overview.schemas import (
    CATEGORIES,
    OverviewFilterQuery,
    OverviewItemDetail,
    OverviewItemRow,
    OverviewItemsQuery,
    OverviewKpi,
    UnattributedOut,
    WarehouseOut,
)
from app.modules.pmc_overview.snapshot import OverviewBoard

_ROW_FIELDS = set(OverviewItemRow.model_fields)


def _matches(r: dict[str, Any], q: OverviewFilterQuery) -> bool:
    if q.store_id and not any(s.get("id") == q.store_id for s in r["stores"]):
        return False
    if q.owner and r["owner"] != q.owner:
        return False
    if q.cats and not all(c in r["cats"] for c in q.cats):
        return False
    if q.only_issue and not r["issues"]:
        return False
    kw = (q.keyword or "").strip().lower()
    if kw:
        hay = (
            r["item_id"],
            r["draft_id"].lower(),
            r["sku"].lower(),
            r["msku"].lower(),
            r["name"].lower(),
        )
        if not any(kw in h for h in hay):
            return False
    return True


def row_out(r: dict[str, Any]) -> OverviewItemRow:
    return OverviewItemRow(**{k: v for k, v in r.items() if k in _ROW_FIELDS})


def filter_rows(board: OverviewBoard, q: OverviewFilterQuery) -> list[dict[str, Any]]:
    return [r for r in board.rows if _matches(r, q)]


def _sorted(rows: list[dict[str, Any]], q: OverviewItemsQuery) -> list[dict[str, Any]]:
    if q.sort_by is None:
        return rows  # snapshot order = 8088 problem priority
    key = q.sort_by
    present = [r for r in rows if r.get(key) is not None]
    missing = [r for r in rows if r.get(key) is None]
    present.sort(key=lambda r: (r[key], r["item_id"]), reverse=q.sort_order == "desc")
    return present + missing  # empty values always last


def category_counts(board: OverviewBoard, q: OverviewFilterQuery) -> dict[str, int]:
    base = q.model_copy(update={"cats": []})
    counts = dict.fromkeys(CATEGORIES, 0)
    for r in board.rows:
        if _matches(r, base):
            for c in r["cats"]:
                if c in counts:
                    counts[c] += 1
    return counts


def list_items(board: OverviewBoard, q: OverviewItemsQuery) -> tuple[list[OverviewItemRow], int]:
    rows = _sorted(filter_rows(board, q), q)
    start = (q.page - 1) * q.page_size
    return [row_out(r) for r in rows[start : start + q.page_size]], len(rows)


def item_detail(board: OverviewBoard, item_id: str) -> OverviewItemDetail | None:
    r = board.row(item_id)
    if r is None:
        return None
    keep = _ROW_FIELDS | {"batches", "dom_rows", "plans_recent"}
    return OverviewItemDetail(**{k: v for k, v in r.items() if k in keep})


def kpi_out(board: OverviewBoard) -> OverviewKpi:
    return OverviewKpi(**board.kpi)


def unattributed_out(board: OverviewBoard) -> list[UnattributedOut]:
    return [
        UnattributedOut(kind=str(x["kind"]), why=str(x["why"]), qty=int(x["qty"]))
        for x in board.unattributed
    ]


def warehouses_out(board: OverviewBoard, *, only_stocked: bool) -> list[WarehouseOut]:
    out = []
    for w in board.warehouses:
        if only_stocked and not (w.get("total", 0) > 0 and w.get("class") in ("国内仓", "海外仓")):
            continue
        age = board.domestic_age.get(w["name"]) or {}
        out.append(
            WarehouseOut(
                name=w["name"],
                warehouse_class=w.get("class") or "",
                valid=int(w.get("valid") or 0),
                lock=int(w.get("lock") or 0),
                total=int(w.get("total") or 0),
                onway=int(w.get("onway") or 0),
                skus=int(w.get("skus") or 0),
                age_avg=age.get("avg"),
                age_max=age.get("max"),
                age_bands={k: int(v) for k, v in (age.get("bands") or {}).items()},
            )
        )
    return out


def categories() -> list[str]:
    return list(CATEGORIES)
