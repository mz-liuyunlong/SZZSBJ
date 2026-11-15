"""PR337 new-products-only, READ-ONLY purchase-time reconciliation for unfrozen V4/V5/V6 views.

This file deliberately does NOT modify global Order V2 sync, facts, MARTs,
production history, scoring rules, other product pages or approval workflows.
The local endpoint reads a bounded page and ONLY projects verified facts when
order-line versions, purchase-date daily buckets and saved SaleStat match.
Production remains disabled until the normal background scoring job is updated
and separately approved; never perform live warehouse reconciliation in prod GET.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

LOG = logging.getLogger(__name__)
LA = ZoneInfo("America/Los_Angeles")
CHINA = ZoneInfo("Asia/Shanghai")
VERSION = "PR337_NEW_PRODUCTS_MART_AUTHORITY_V3_20261115"
_ALLOWED_SOURCE_MARKERS = frozenset({
    "PR337_SALESTAT_PERSISTED_VIEW_V5_20261114",
    "PR337_SQL_ATTESTED_CURRENT_VIEW_V6_20261114",
})
MAX_PAGE = 200
MAX_FACT_ROWS = 20000

# All SQL is SELECT only and uses bound JSON scopes; no SQL joins across page
# routes, independent schemas, or mutable operational source tables.
_SNAPSHOTS_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,p.metric_window_start_la AS start_day,
       p.metric_window_end_la AS end_day,p.sales_orders,p.sales_units,
       p.data_coverage_json AS coverage
FROM wanted w
JOIN biz_new_product_registry r
  ON r.source_account_ref=w.account AND r.store_id=w.store AND r.item_id=w.item
JOIN biz_new_product_performance_current p ON p.registry_id=r.id
""")

_MART_SQL = text("""
WITH wanted AS (
 SELECT account,store,item,start_date,end_date
 FROM jsonb_to_recordset(CAST(:windows AS jsonb))
 AS j(account text,store text,item text,start_date date,end_date date)
)
SELECT w.account,w.store,w.item,d.business_date_la AS day,
       d.order_count,d.sales_qty
FROM wanted w JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN w.start_date AND w.end_date
ORDER BY w.account,w.store,w.item,d.business_date_la
""")

_FACT_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,f.source_order_id,f.source_order_line_id,
       f.quantity,f.source_purchase_at_raw,f.is_identity_current,
       f.is_sample_order,f.order_status_raw,f.business_date_la,
       EXISTS (
           SELECT 1 FROM fact_walmart_order_items other
           WHERE other.source_account_ref=f.source_account_ref
             AND other.store_id=f.store_id
             AND other.source_order_id=f.source_order_id
             AND other.source_order_line_id=f.source_order_line_id
             AND other.item_id IS DISTINCT FROM f.item_id
       ) AS cross_item_lineage
FROM wanted w JOIN fact_walmart_order_items f
 ON f.source_account_ref=w.account AND f.store_id=w.store AND f.item_id=w.item
ORDER BY w.account,w.store,w.item,f.source_order_id,f.source_order_line_id,
         f.business_date_la
LIMIT :max_rows
""")


def _as_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["account"]), str(row["store"]), str(row["item"]))


def _natural(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return int(num) if num.is_finite() and num >= 0 and num == num.to_integral_value() else None


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return num if num.is_finite() and num >= 0 else None


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def purchase_day(raw: Any) -> date | None:
    """Order V2: Unix timestamps are UTC instants; naive textual times use China time."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, str)):
        value = str(raw).strip()
        if re.fullmatch(r"[0-9]{10}", value):
            seconds = int(value)
        elif re.fullmatch(r"[0-9]{13}", value):
            seconds = int(value) / 1000
        else:
            seconds = None
        if seconds is not None:
            try:
                parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
                return parsed.astimezone(LA).date() if 2000 <= parsed.year <= 2100 else None
            except (ValueError, OverflowError, OSError):
                return None
        # Other digit-length timestamps are unknown, NOT local calendar dates.
        if value.isdigit():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CHINA)
        return parsed.astimezone(LA).date() if 2000 <= parsed.year <= 2100 else None
    if isinstance(raw, datetime):
        parsed = raw if raw.tzinfo is not None else raw.replace(tzinfo=CHINA)
        return parsed.astimezone(LA).date()
    return None


def _line_units(records: list[dict[str, Any]]) -> tuple[date, int] | None:
    """One purchase line can have many physical history versions, but one value."""
    purchase_days = {purchase_day(r.get("source_purchase_at_raw")) for r in records}
    qty = {_natural(r.get("quantity")) for r in records}
    if (None in purchase_days or len(purchase_days) != 1
            or None in qty or 0 in qty or len(qty) != 1):
        return None
    if any(bool(r.get("cross_item_lineage")) for r in records):
        return None
    if sum(r.get("is_identity_current") is True for r in records) > 1:
        return None
    status = {
        str(r.get("order_status_raw") or "").strip().upper() in
        {"CANCELED", "CANCELLED", "CANCEL", "VOID"}
        for r in records
    }
    samples = {r.get("is_sample_order") for r in records}
    if len(status) != 1 or samples != {False} or True in status:
        return None
    return next(iter(purchase_days)), next(iter(qty))


def _reconstruct(start: date, end: date, physical_rows: list[dict[str, Any]]) -> dict[date, tuple[int, int, int]] | None:
    """Group versions by line, then lines by order; fail closed on ambiguous identities."""
    lines: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in physical_rows:
        order, line = str(r.get("source_order_id") or "").strip(), str(r.get("source_order_line_id") or "").strip()
        if not order or not line:
            return None  # Unattributable physical row: no manufactured order.
        lines[(order, line)].append(r)
    orders: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for (order, _), versions in lines.items():
        one = _line_units(versions)
        if one is None:
            return None
        orders[order].append(one)
    daily: dict[date, list[int]] = defaultdict(list)
    for order_lines in orders.values():
        days = {d for d, _ in order_lines}
        if len(days) != 1:
            return None
        day = next(iter(days))
        if not start <= day <= end:
            continue  # Valid purchases outside the observation window are excluded.
        qty = sum(q for _, q in order_lines)
        daily[day].append(qty)
    return {d: (len(qtys), sum(qtys), sum(q == 1 for q in qtys)) for d, qtys in daily.items()}


def verify_window(start: date, end: date, mart_rows: list[dict[str, Any]],
                  fact_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Only a full 14-day, EXACT day/order/unit match produces score evidence."""
    if not isinstance(start, date) or not isinstance(end, date) or end != start + timedelta(days=13):
        return None
    if not mart_rows:
        return None  # No MART data is *unknown*, never zero sales.
    paid: dict[date, list[int]] = {}
    for r in mart_rows:
        day, orders, qty = _day(r.get("day")), _natural(r.get("order_count")), _natural(r.get("sales_qty"))
        if day is None or not start <= day <= end or orders is None or qty is None or qty < orders:
            return None
        # Daily SaleStat is unique per item+day. Do not let duplicated rows
        # accidentally reconcile to a duplicated order sample.
        if day in paid:
            return None
        paid[day] = [orders, qty]
    details = _reconstruct(start, end, fact_rows)
    if details is None:
        return None
    for i in range(14):
        day = start + timedelta(days=i)
        po, pu = paid.get(day, [0, 0])
        fo, fu, _ = details.get(day, (0, 0, 0))
        if (po, pu) != (fo, fu):
            return None
    orders = sum(v[0] for v in paid.values())
    units = sum(v[1] for v in paid.values())
    singles = sum(v[2] for v in details.values())
    first = min((d for d, (n, _) in paid.items() if n > 0), default=None)
    if orders < 1 or units < orders or singles > orders:
        return None  # Zero-order scoring belongs to the existing rule path.
    return {"orders": orders, "units": units, "singles": singles, "first_date": first}




def mart_window_evidence(start: date, end: date,
                         mart_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Independent SaleStat proof; no Order V2 dates, identities or version flags.

    Validates the exact frozen 14-day window including unique, nonnegative day
    totals. This is the *only* input allowed to determine speed's orders/day.
    """
    if (not isinstance(start, date) or not isinstance(end, date)
            or end != start + timedelta(days=13) or not mart_rows):
        return None
    paid: dict[date, tuple[int, int]] = {}
    for r in mart_rows:
        day = _day(r.get("day"))
        orders = _natural(r.get("order_count"))
        qty = _natural(r.get("sales_qty"))
        if (day is None or not start <= day <= end or day in paid
                or orders is None or qty is None or qty < orders
                or (orders == 0 and qty != 0)):
            return None
        paid[day] = (orders, qty)
    total_orders = sum(v[0] for v in paid.values())
    total_units = sum(v[1] for v in paid.values())
    first = min((d for d, (n, _) in paid.items() if n > 0), default=None)
    if total_orders <= 0 or first is None:
        return None  # Unknown/zero-order scores are handled by existing rules.
    return {"orders": total_orders, "units": total_units,
            "first_date": first, "paid_days": paid}


def verify_mart_paid_sample(start: date, end: date,
                            mart_rows: list[dict[str, Any]],
                            fact_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Trust ONLY when SaleStat-positive dates have provably correct order mix.

    Order V2 may report paid-looking orders on days where authoritative SaleStat
    has 0; those cannot enter this *paid* measurement population. A one-order
    surplus on a SaleStat-positive date is allowed only if every observed order
    on that day is 1 unit AND MART itself proves all paid orders are 1 unit.
    No arbitrary line or order is selected; if the singles ratio is not uniquely
    determined, this returns None and trust is not scored.
    """
    trusted = mart_window_evidence(start, end, mart_rows)
    if trusted is None:
        return None
    reconstructed = _reconstruct(start, end, fact_rows)
    if reconstructed is None:
        return None
    paid = trusted["paid_days"]
    excluded_orders = 0
    excluded_units = 0
    inferred_paid_days = 0
    singles = 0
    for i in range(14):
        day = start + timedelta(days=i)
        po, pu = paid.get(day, (0, 0))
        fo, fu, fs = reconstructed.get(day, (0, 0, 0))
        if (po, pu) == (fo, fu):
            singles += fs
        elif po == pu == 0 and fo > 0:
            # Not an observed paid sale; exclude whole day, not selected order IDs.
            excluded_orders += fo
            excluded_units += fu
        elif (po > 0 and pu == po and fo == po + 1 and fu == fo
              and fs == fo):
            # MART proves every paid order is one unit; candidate set is also
            # all one-unit. Only the count matters, not which ID was included.
            singles += po
            inferred_paid_days += 1
        else:
            return None
    if excluded_orders == 0 and inferred_paid_days == 0:
        return None  # Exact matches must use the existing strict path.
    if not 0 <= singles <= trusted["orders"]:
        return None
    return {"orders": trusted["orders"], "units": trusted["units"],
            "singles": singles, "first_date": trusted["first_date"],
            "paid_day_mode": "MART_AUTHORIZED_PAID_SAMPLE",
            "excluded_order_v2_orders": excluded_orders,
            "excluded_order_v2_units": excluded_units,
            "all_single_day_inferences": inferred_paid_days}


def _verified_mart_provenance(row: dict[str, Any], snap: dict[str, Any],
                              proof: dict[str, Any]) -> bool:
    """Verify preserved read-only V4/MART totals without gating speed on FACT."""
    facts, ev = row.get("facts"), row.get("evaluation")
    if not isinstance(facts, dict) or not isinstance(ev, dict):
        return False
    if ev.get("observation_state") != "automatic_partial" or _natural(ev.get("rule_version")) != 0:
        return False
    coverage = snap.get("coverage")
    if not isinstance(coverage, dict):
        return False
    saved, quality = coverage.get("auto_dimension_scores"), coverage.get("rebuild_quality")
    if not isinstance(saved, dict) or not isinstance(quality, dict):
        return False
    start, end = _day(snap.get("start_day")), _day(snap.get("end_day"))
    if start is None or end != start + timedelta(days=13):
        return False
    if (saved.get("scoring_provenance") != "PR337_SOURCE_REBUILD_V4"
            or _natural(saved.get("rule_version")) != 0
            or quality.get("source_consistency") != "MART_ORDER_FACT_MISMATCH"
            or _natural(quality.get("rule_version")) != 0
            or quality.get("source_date_start_la") != start.isoformat()
            or quality.get("source_date_end_la") != end.isoformat()):
        return False
    rect = facts.get("order_reconciliation")
    if not isinstance(rect, dict) or rect.get("version") not in _ALLOWED_SOURCE_MARKERS:
        return False
    for value in (snap.get("sales_orders"), quality.get("mart_orders"), rect.get("mart_orders")):
        if _natural(value) != proof["orders"]:
            return False
    for value in (snap.get("sales_units"), quality.get("mart_units"), rect.get("mart_units")):
        if _natural(value) != proof["units"]:
            return False
    if _day(facts.get("first_wfs_available_date_la")) not in (None, start):
        return False
    return True


def _summarize_dimensions(ev: dict[str, Any]) -> None:
    """Existing V5/V6 read-only partial totals, unchanged other dimensions."""
    dims = ev["dimensions"]
    ev["total"] = None
    ev["grade"] = None
    ev["automatic_points"] = str(sum(
        (_number(dims.get(k)) or Decimal(0)) * Decimal(DEFAULT_WEIGHTS[k]) / 100
        for k in ("speed", "ad", "profit", "trust")
    ))
    ev["covered_weight_pct"] = sum(
        DEFAULT_WEIGHTS[k] for k in ("speed", "ad", "profit", "trust")
        if dims.get(k) is not None
    )


def apply_mart_speed(row: dict[str, Any], proof: dict[str, Any],
                     *, start: date) -> bool:
    """Repair speed from independent paid-sale MART even if Order V2 disagrees."""
    facts, ev = row["facts"], row["evaluation"]
    dims = ev.get("dimensions")
    if not isinstance(dims, dict) or _day(facts.get("first_wfs_available_date_la")) not in (None, start):
        return False
    day = (proof["first_date"] - start).days + 1
    if not 1 <= day <= 14:
        return False
    calculated = evaluate({
        "market_score": None, "elapsed_days": 14,
        "first_order_day": day, "effective_orders_14d": proof["orders"],
        "ad_status": "unknown",
    }, {"confirmedScoring": DEFAULT_PARAMETERS, "weights": DEFAULT_WEIGHTS}, 0)
    speed = calculated["dimensions"].get("speed")
    if speed is None:
        return False
    # Leave existing independently verified trust (if any) and all other scores.
    dims["speed"] = speed
    facts.update({
        "first_order_day": day,
        "effective_orders_14d": proof["orders"],
        "valid_orders_14d": proof["orders"],
        "valid_units_14d": str(proof["units"]),
        "observation_first_order_date_la": proof["first_date"].isoformat(),
        "order_unit_display_source": "mart_daily_sales_item_day",
        "speed_evidence_source": "MART_SALESTAT_VERIFIED_WINDOW_V3",
    })
    if dims.get("trust") is None:
        facts["single_unit_orders_14d"] = None
        facts["trust_evidence_source"] = "ORDER_DETAIL_DISTRIBUTION_NOT_YET_VERIFIED"
    _summarize_dimensions(ev)
    if "suggested_qty" in row:
        row["suggested_qty"] = None
    return True



def read_paid_order_summary(session: Any, account: str, store: str, item: str,
                            start: date, end: date,
                            mart_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Single-listing detail/score parity, using the same strict paid-day proof.

    No persisted snapshot or local-view mutation here. A missing/uncertain
    Order V2 source simply returns None; MART speed remains independent.
    """
    if os.getenv("APP_ENV", "").strip().lower() not in {"local", "dev", "development"}:
        return None
    if mart_window_evidence(start, end, mart_rows) is None:
        return None
    if not all((account, store, item)) or any(len(v) > 200 for v in (account, store, item)):
        return None
    wanted = json.dumps([{"account": account, "store": store, "item": item}])
    try:
        source = list(session.execute(_FACT_SQL, {
            "wanted": wanted, "max_rows": MAX_FACT_ROWS+1
        }).mappings())
        if len(source) > MAX_FACT_ROWS:
            return None
        facts = [dict(r) for r in source if _as_key(r) == (account, store, item)]
        result = verify_window(start, end, mart_rows, facts)
        return result if result is not None else verify_mart_paid_sample(start, end, mart_rows, facts)
    except Exception as exc:
        LOG.warning("new_products_paid_detail_reconcile=read_failed type=%s", type(exc).__name__)
        return None

def _candidate(row: dict[str, Any]) -> tuple[str, str, str] | None:
    if not isinstance(row, dict):
        return None
    listing, facts, ev = row.get("listing"), row.get("facts"), row.get("evaluation")
    if not isinstance(listing, dict) or not isinstance(facts, dict) or not isinstance(ev, dict):
        return None
    if ev.get("observation_state") != "automatic_partial" or _natural(ev.get("rule_version")) != 0:
        return None
    rect = facts.get("order_reconciliation")
    if not isinstance(rect, dict) or rect.get("version") not in _ALLOWED_SOURCE_MARKERS:
        return None
    keys = tuple(str(listing.get(k) or "").strip() for k in ("source_account_ref", "store_id", "item_id"))
    return keys if all(keys) else None


def _verified_source(row: dict[str, Any], snap: dict[str, Any],
                     verified: dict[str, Any]) -> bool:
    facts, rect = row["facts"], row["facts"]["order_reconciliation"]
    coverage = snap.get("coverage")
    if not isinstance(coverage, dict):
        return False
    saved, quality = coverage.get("auto_dimension_scores"), coverage.get("rebuild_quality")
    if not isinstance(saved, dict) or not isinstance(quality, dict):
        return False
    start, end = _day(snap.get("start_day")), _day(snap.get("end_day"))
    if start is None or end is None or end != start + timedelta(days=13):
        return False
    if (saved.get("scoring_provenance") != "PR337_SOURCE_REBUILD_V4"
            or _natural(saved.get("rule_version")) != 0
            or quality.get("source_consistency") != "MART_ORDER_FACT_MISMATCH"
            or _natural(quality.get("rule_version")) != 0
            or _natural(quality.get("invalid_source_lines")) != 0
            or quality.get("source_date_start_la") != start.isoformat()
            or quality.get("source_date_end_la") != end.isoformat()):
        return False
    if (_natural(snap.get("sales_orders")) != verified["orders"]
            or _natural(snap.get("sales_units")) != verified["units"]
            or _natural(quality.get("mart_orders")) != verified["orders"]
            or _natural(quality.get("mart_units")) != verified["units"]
            or _natural(rect.get("mart_orders")) != verified["orders"]
            or _natural(rect.get("mart_units")) != verified["units"]):
        return False
    # Keep the exact historical V4 mismatch identity, not some unrelated row.
    if (_natural(quality.get("order_fact_orders")) != _natural(rect.get("current_fact_orders"))
            or _natural(quality.get("order_fact_units")) != _natural(rect.get("current_fact_units"))):
        return False
    if _day(facts.get("first_wfs_available_date_la")) not in (None, start):
        return False
    return True


def apply_verified(row: dict[str, Any], verified: dict[str, Any], *, start: date | None = None) -> bool:
    """Mutates only ephemeral API response dictionaries; no persisted entities."""
    ev, facts = row["evaluation"], row["facts"]
    snap_start = start
    start = _day(facts.get("first_wfs_available_date_la")) or snap_start
    if start is None or (snap_start is not None and start != snap_start):
        return False
    first = verified["first_date"]
    day = (first-start).days + 1
    if not 1 <= day <= 14:
        return False
    params = {"confirmedScoring": DEFAULT_PARAMETERS, "weights": DEFAULT_WEIGHTS}
    scores = evaluate({
        "market_score": None, "elapsed_days": 14,
        "first_order_day": day, "effective_orders_14d": verified["orders"],
        "valid_units_14d": verified["units"], "valid_orders_14d": verified["orders"],
        "single_unit_orders_14d": verified["singles"], "ad_status": "unknown",
    }, params, 0)
    dims = ev.get("dimensions")
    if not isinstance(dims, dict):
        return False
    speed, trust = scores["dimensions"].get("speed"), scores["dimensions"].get("trust")
    if speed is None or trust is None:
        return False
    # Apply only after every read-only source and scoring gate has passed.
    dims["speed"], dims["trust"] = speed, trust
    facts.update({
        "first_order_day": day,
        "effective_orders_14d": verified["orders"],
        "valid_orders_14d": verified["orders"],
        "valid_units_14d": str(verified["units"]),
        "single_unit_orders_14d": verified["singles"],
        "speed_evidence_source": VERSION,
        "trust_evidence_source": VERSION,
        "observation_first_order_date_la": first.isoformat(),
    })
    prior = facts["order_reconciliation"]
    facts["order_reconciliation"] = {
        **prior,
        "version": VERSION,
        "decision": ("MART_PAID_SAMPLE_CHECKED" if verified.get("paid_day_mode")
                         else "PURCHASE_TIME_DAILY_EXACT_MATCH"),
        "excluded_order_v2_orders": verified.get("excluded_order_v2_orders", 0),
        "all_single_day_inferences": verified.get("all_single_day_inferences", 0),
        "verified_orders": verified["orders"],
        "verified_units": verified["units"],
        "verified_singles": verified["singles"],
    }
    ev["total"] = None
    ev["grade"] = None
    ev["automatic_points"] = str(sum(
        (_number(dims.get(k)) or Decimal(0)) * Decimal(DEFAULT_WEIGHTS[k]) / 100
        for k in ("speed", "ad", "profit", "trust")
    ))
    ev["covered_weight_pct"] = sum(
        DEFAULT_WEIGHTS[k] for k in ("speed", "ad", "profit", "trust") if dims.get(k) is not None
    )
    old_missing = ev.get("missing")
    if isinstance(old_missing, list):
        ev["missing"] = [m for m in old_missing if m != "FACT与MART订单数或销售件数不一致，数据可信度待核实"]
    facts["data_status"] = "partial"  # Still missing market/manual and B1 evidence.
    if "suggested_qty" in row:
        row["suggested_qty"] = None
    return True


def reconcile_pending_rows(session: Any, rows: list[dict[str, Any]]) -> None:
    """V3 local-only ephemeral projection; MART speed, proven paid-order trust."""
    if os.getenv("APP_ENV", "").strip().lower() not in {"local", "dev", "development"}:
        return
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = _candidate(row)
        if key is not None:
            candidates[key] = row
    if not candidates or len(candidates) > MAX_PAGE:
        return
    wanted = json.dumps([{"account": a, "store": s, "item": i} for a, s, i in candidates])
    try:
        snaps = {_as_key(r): dict(r) for r in session.execute(_SNAPSHOTS_SQL, {"wanted": wanted}).mappings()}
        windows: list[dict[str, str]] = []
        for key, row in candidates.items():
            snap = snaps.get(key)
            if snap is None:
                continue
            start, end = _day(snap.get("start_day")), _day(snap.get("end_day"))
            if start is None or end != start + timedelta(days=13):
                continue
            if end >= datetime.now(LA).date():
                continue  # No frozen conclusions while observation window is active.
            windows.append({"account": key[0], "store": key[1], "item": key[2],
                            "start_date": start.isoformat(), "end_date": end.isoformat()})
        if not windows:
            return
        marts: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in session.execute(_MART_SQL, {"windows": json.dumps(windows)}).mappings():
            marts[_as_key(r)].append(dict(r))
        # First collect independent MART proof; FACT has no power to negate speed.
        proven: dict[tuple[str, str, str], dict[str, Any]] = {}
        for w in windows:
            key = _as_key(w)
            snap = snaps[key]
            proof = mart_window_evidence(_day(snap["start_day"]), _day(snap["end_day"]), marts.get(key, []))
            if proof is not None and _verified_mart_provenance(candidates[key], snap, proof):
                proven[key] = proof
        if not proven:
            return
        # Keep the existing bounded read; a failed FDW query may not suppress
        # SaleStat speed if the MART source has already been verified.
        facts: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        fact_ready = False
        try:
            fact_wanted = json.dumps([{"account": a, "store": s, "item": i}
                                      for a, s, i in proven])
            fetched = list(session.execute(_FACT_SQL, {
                "wanted": fact_wanted, "max_rows": MAX_FACT_ROWS+1
            }).mappings())
            if len(fetched) <= MAX_FACT_ROWS:
                fact_ready = True
                for r in fetched:
                    facts[_as_key(r)].append(dict(r))
            else:
                LOG.warning("new_products_mart_authority=skip_unbounded_fact_page")
        except Exception as exc:
            # The outer service already catches unexpected read errors. The
            # authoritative MART speed is still independently provable here.
            LOG.warning("new_products_mart_authority=fact_read_unavailable type=%s", type(exc).__name__)
        count_speed, count_trust = 0, 0
        for w in windows:
            key = _as_key(w)
            proof = proven.get(key)
            if proof is None:
                continue
            snap = snaps[key]
            start, end = _day(snap["start_day"]), _day(snap["end_day"])
            if not fact_ready:
                if apply_mart_speed(candidates[key], proof, start=start):
                    count_speed += 1
                continue
            match = verify_window(start, end, marts[key], facts.get(key, []))
            if match is None:
                match = verify_mart_paid_sample(start, end, marts[key], facts.get(key, []))
            if (match is not None and _verified_source(candidates[key], snap, match)
                    and apply_verified(candidates[key], match, start=start)):
                count_speed += 1
                count_trust += 1
                continue
            if apply_mart_speed(candidates[key], proof, start=start):
                count_speed += 1
        LOG.info("new_products_mart_authority speed_verified=%d trust_verified=%d page=%d",
                 count_speed, count_trust, len(windows))
    except Exception as exc:
        LOG.warning("new_products_mart_authority=read_failed type=%s", type(exc).__name__)
