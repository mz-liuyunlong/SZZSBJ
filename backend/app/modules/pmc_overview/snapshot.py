"""Transitional data source for 5173: one 8088 overview snapshot file (read-only).

PRP pmc-overview §5173 fast path (Rocky 2026-11-03 "按 8088 业务逻辑先上 5173").
The DEMO page's real day data (``daily/20261102``) is exported once into a JSON file on
the developer machine; this module reads it, runs the formal rule layer
(:mod:`calculations`) on the inputs, and serves the board. It never calls Lingxing or
Walmart, never writes the database, and the file never enters the repository.

The file path comes from ``PMC_OVERVIEW_SNAPSHOT_FILE``; unset or unreadable means
"not ready" (HTTP 503) instead of falling back to sample data (R-6: no mock data).
Once the replenishment tables exist, :class:`OverviewBoard` is filled from them instead.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.modules.pmc_overview.calculations import (
    CATEGORY_PRIORITY,
    DraftMode,
    ItemResult,
    compute_all,
    sort_category,
)
from app.modules.pmc_overview.golden import DEMO_KPI_MAP, item_from_dict
from app.modules.pmc_overview.rules import RULE_VERSION_DEFAULT, OverviewParams, params_from_demo

SNAPSHOT_ENV = "PMC_OVERVIEW_SNAPSHOT_FILE"
DRAFT_MODE_ENV = "PMC_OVERVIEW_DRAFT_MODE"
SUPPORTED_VERSION = 1
# Rocky 2026-11-03 (#301): the snapshot is a 5173-only transition; 8443 must never read it.
SNAPSHOT_ALLOWED_ENVS = frozenset({"local", "dev", "test"})


class SnapshotNotReady(Exception):
    """No usable snapshot file (unset, missing, unreadable or wrong version)."""


@dataclass
class OverviewBoard:
    today: str
    source: str
    source_note: str
    rule_version: str
    draft_mode: DraftMode
    params: OverviewParams
    raw_params: dict[str, int]  # 8088 keys incl. replenishment ones (rules tab shows all)
    kpi: dict[str, int]
    parity: dict[str, dict[str, int]]  # KPI diff vs. the 8088 page (empty = identical)
    rows: list[dict[str, Any]]
    stores: list[dict[str, str]]
    owners: list[str]
    store_summary: list[dict[str, Any]] = field(default_factory=list)
    warehouses: list[dict[str, Any]] = field(default_factory=list)
    domestic_age: dict[str, Any] = field(default_factory=dict)
    unattributed: list[dict[str, Any]] = field(default_factory=list)
    overseas_total: int = 0
    ops: dict[str, Any] = field(default_factory=dict)

    def row(self, item_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rows if r["item_id"] == item_id), None)


def _issue_list(issues: list[Any]) -> list[dict[str, str]]:
    return [{"label": i.label, "level": i.level, "detail": i.detail} for i in issues]


def _row(display: dict[str, Any], inp: dict[str, Any], r: ItemResult, sort_cat: str) -> dict:
    return {
        "item_id": r.item_id,
        "sku": r.sku,
        "msku": display.get("msku") or "",
        "name": display.get("name") or "",
        "owner": display.get("owner") or "",
        "stores": display.get("stores") or [],
        "listing": inp.get("listing") or "",
        "tags": list(inp.get("tags") or []),
        "daily": float(inp["daily"]),
        "n30": int(inp["n30"]),
        "n_window": display.get("n_window"),
        "oos_days": inp.get("oos_days"),
        "no_stock_90": bool(inp["no_stock_90"]),
        "supply": int(inp["supply"]),
        "wm_available": int(inp.get("wm_available") or 0),
        "seg": display.get("seg") or {},
        "dom_lock": int(display.get("dom_lock") or 0),
        "sellout": inp.get("sellout"),
        "gap_days": inp.get("gap_days"),
        "resume": inp.get("resume"),
        "next_date": inp.get("next_date"),
        "lead_total": float(inp["lead_total"]),
        "lead_p": display.get("lead_p"),
        "lead_avg": inp.get("lead_avg"),
        "cycle_days": display.get("cycle_days"),
        "suggest": int(inp["suggest"]),
        "suggest_raw": int(inp["suggest_raw"]),
        "capped": bool(inp["capped"]),
        "box": int(inp.get("box") or 0),
        "cover": r.cover,
        "over": r.over,
        "stale": r.stale,
        "risk": r.risk,
        "oos": r.oos,
        "low_days": r.low_days,
        "listing_bad": r.listing_bad,
        "dom_over_qty": r.dom_over_qty,
        "dom_max": r.dom_max,
        "overseas_total": r.overseas_total,
        "overseas_alloc": r.overseas_alloc,
        "purchase": r.purchase,
        "boxed": r.boxed,
        "is_draft": r.is_draft,
        "draft_id": inp.get("draft_id") or "",
        "draft_text": r.draft_text,
        "issues": _issue_list(r.issues),
        "sc_flags": _issue_list(r.sc_flags),
        "exec_flags": _issue_list(r.exec_flags),
        "main": r.main,
        "level": r.level,
        "cats": r.cats,
        "sort_cat": sort_cat,
        "batches": display.get("batches") or [],
        "dom_rows": display.get("dom_rows") or [],
        "plans_recent": inp.get("plans_recent") or [],
    }


def build_board(snap: dict[str, Any], draft_mode: DraftMode = "replenishment") -> OverviewBoard:
    if snap.get("version") != SUPPORTED_VERSION or not isinstance(snap.get("items"), list):
        raise SnapshotNotReady("unsupported snapshot format")
    params = params_from_demo(snap.get("params") or {})
    today = str(snap["today"])
    items = [item_from_dict(x["input"]) for x in snap["items"]]
    results, kpi = compute_all(items, params, today, draft_mode)
    rows = []
    for x, it, r in zip(snap["items"], items, results, strict=True):
        rows.append(_row(x.get("display") or {}, x["input"], r, sort_category(it, r)))
    # 8088 App list order: category priority, sell-out date (none last), larger supply first.
    rows.sort(
        key=lambda r: (
            CATEGORY_PRIORITY.get(r["sort_cat"], 99),
            r["sellout"] or "9",
            -r["supply"],
        )
    )
    expected = snap.get("expected_kpi") or {}
    parity = {
        k: {"demo": int(expected[k]), "ours": kpi[v]}
        for k, v in DEMO_KPI_MAP.items()
        if k in expected and int(expected[k]) != kpi[v]
    }
    owners = sorted({r["owner"] for r in rows if r["owner"]})
    return OverviewBoard(
        today=today,
        source=str(snap.get("source") or ""),
        source_note=str(snap.get("src") or ""),
        rule_version=RULE_VERSION_DEFAULT,
        draft_mode=draft_mode,
        params=params,
        raw_params={str(k): int(v) for k, v in (snap.get("params") or {}).items()},
        kpi=kpi,
        parity=parity,
        rows=rows,
        stores=[{"id": str(s["id"]), "name": str(s["name"])} for s in snap.get("stores") or []],
        owners=owners,
        store_summary=list(snap.get("store_summary") or []),
        warehouses=list(snap.get("warehouses") or []),
        domestic_age=dict(snap.get("domestic_age") or {}),
        unattributed=list(snap.get("unattributed_detail") or []),
        overseas_total=int(snap.get("overseas_total") or 0),
        ops=dict(snap.get("ops") or {}),
    )


_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "board": None}


def _draft_mode() -> DraftMode:
    # PRP D3 = a (Rocky 2026-11-03): drafts follow the replenishment page (87 on 2026-11-02,
    # not the 113 the 8088 overview page judged itself). demo_8088 is only for golden checks.
    return "demo_8088" if os.getenv(DRAFT_MODE_ENV) == "demo_8088" else "replenishment"


def load_board() -> OverviewBoard:
    """Return the board for the configured snapshot; cached until the file changes."""
    if os.getenv("APP_ENV", "").strip().lower() not in SNAPSHOT_ALLOWED_ENVS:
        raise SnapshotNotReady("snapshot source is local-only")
    raw = os.getenv(SNAPSHOT_ENV, "").strip()
    if not raw:
        raise SnapshotNotReady("snapshot path not configured")
    path = Path(raw)
    try:
        stat = path.stat()
    except OSError as exc:
        raise SnapshotNotReady("snapshot file missing") from exc
    mode = _draft_mode()
    key = (str(path), stat.st_mtime_ns, stat.st_size, mode)
    with _lock:
        if _cache["key"] == key:
            return _cache["board"]
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
            board = build_board(snap, mode)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SnapshotNotReady("snapshot file unreadable") from exc
        _cache.update(key=key, board=board)
        return board


def clear_cache() -> None:
    with _lock:
        _cache.update(key=None, board=None)
