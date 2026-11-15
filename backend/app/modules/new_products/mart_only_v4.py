"""PR337 local-only MART deterministic speed/trust evidence (V5).

Only reads saved new-product snapshot + scoped SaleStat daily MART. For any
individual business day, if the order/units totals uniquely determine the
number of single-unit orders, Order V2 isn't required. Otherwise fail closed.
Never writes database, changes scores already present, or changes finalized
records. Only projects ephemeral API response dictionaries.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

LOG = logging.getLogger(__name__)
LA = ZoneInfo("America/Los_Angeles")
VERSION = "PR337_MART_ONLY_DETERMINISTIC_V5_20261115"
MAX_PAGE = 200
MAX_MART_ROWS = 5000

_SNAP_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,p.metric_window_start_la AS start_day,
       p.metric_window_end_la AS end_day,p.first_order_date_la AS saved_first_day,
       p.sales_orders,p.sales_units,
       first_stock.first_wfs_available_date_la AS locked_first_wfs_day
FROM wanted w
JOIN biz_new_product_registry r
  ON r.source_account_ref=w.account AND r.store_id=w.store AND r.item_id=w.item
JOIN biz_new_product_performance_current p ON p.registry_id=r.id
LEFT JOIN listing_wfs_first_stock_la_locked first_stock
  ON first_stock.source_account_ref=w.account
 AND first_stock.store_id=w.store AND first_stock.item_id=w.item
""")

_MART_SQL = text("""
WITH wanted AS (
 SELECT account,store,item,start_date,end_date FROM
 jsonb_to_recordset(CAST(:windows AS jsonb))
 AS j(account text,store text,item text,start_date date,end_date date)
)
SELECT w.account,w.store,w.item,d.business_date_la AS day,
       d.order_count,d.sales_qty
FROM wanted w JOIN mart_daily_sales_item_day d
  ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN w.start_date AND w.end_date
ORDER BY w.account,w.store,w.item,d.business_date_la
LIMIT :limit
""")


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _whole(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return (
        int(number)
        if number.is_finite() and number >= 0 and number == number.to_integral_value()
        else None
    )


def _key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(str(record[k]) for k in ("account", "store", "item"))


def mart_deterministic_evidence(
    start: date, end: date, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    """Infer singles only where every daily positive-integer partition is unique.

    With N orders, N units: all N are single-unit orders.
    With N orders, N+1 units: exactly one 2-unit order, N-1 singles.
    With one order and K units: singles=1 iff K=1, else 0.
    Any other daily distribution is ambiguous and must NOT be inferred.
    """
    if (
        not isinstance(start, date)
        or not isinstance(end, date)
        or end != start + timedelta(days=13)
        or not rows
    ):
        return None
    observed: set[date] = set()
    first = None
    orders = units = singles = 0
    for record in rows:
        day, n, q = (
            _day(record.get("day")),
            _whole(record.get("order_count")),
            _whole(record.get("sales_qty")),
        )
        if (
            day is None
            or day in observed
            or not start <= day <= end
            or n is None
            or q is None
            or q < n
            or (n == 0 and q != 0)
        ):
            return None
        observed.add(day)
        if n == 0 or q == n:
            single = n
        elif n == 1:
            single = 0
        elif q == n + 1:
            single = n - 1
        else:
            return None
        orders += n
        units += q
        singles += single
        if n > 0:
            first = min(first, day) if first is not None else day
    if orders <= 0 or first is None or units < orders or singles > orders:
        return None
    return {"orders": orders, "units": units, "singles": singles, "first_date": first}


def _eligible(row: Any) -> tuple[str, str, str] | None:
    if not isinstance(row, dict):
        return None
    listing, facts, evaluation = row.get("listing"), row.get("facts"), row.get("evaluation")
    if not all(isinstance(v, dict) for v in (listing, facts, evaluation)):
        return None
    if (
        evaluation.get("observation_state") != "automatic_partial"
        or _whole(evaluation.get("rule_version")) != 0
        or evaluation.get("total") is not None
        or evaluation.get("grade") is not None
    ):
        return None
    dims = evaluation.get("dimensions")
    if not isinstance(dims, dict):
        return None
    if dims.get("speed") is not None and dims.get("trust") is not None:
        return None  # V6/V3 already verified scores are never overwritten.
    key = tuple(
        str(listing.get(k) or "").strip() for k in ("source_account_ref", "store_id", "item_id")
    )
    if not all(key) or any(len(k) > 200 for k in key):
        return None
    return key


def _wfs_start_verified(row: Mapping[str, Any], snap: Mapping[str, Any], start: date) -> bool:
    """Use authoritative locked WFS start; reject contradictory view metadata.

    Old saved V5/V6 display views may omit facts.first_wfs_available_date_la;
    absence is not itself a reason to discard an independently verified window.
    Never accept a different explicit day, or an entirely unverified first day.
    """
    facts = row.get("facts")
    listing = row.get("listing")
    if not isinstance(facts, dict) or not isinstance(listing, dict):
        return False
    proven = False
    for value in (
        snap.get("locked_first_wfs_day"),
        facts.get("first_wfs_available_date_la"),
        listing.get("first_wfs_available_date_la"),
    ):
        if value is None or value == "":
            continue
        day = _day(value)
        if day is None or day != start:
            return False
        proven = True
    return proven


def _source_matches(
    row: dict[str, Any], snap: Mapping[str, Any], evidence: Mapping[str, Any]
) -> bool:
    start = _day(snap.get("start_day"))
    end = _day(snap.get("end_day"))
    if start is None or end != start + timedelta(days=13) or end >= datetime.now(LA).date():
        return False
    facts = row["facts"]
    if (
        not _wfs_start_verified(row, snap, start)
        or _day(snap.get("saved_first_day")) != evidence["first_date"]
        or _whole(snap.get("sales_orders")) != evidence["orders"]
        or _whole(snap.get("sales_units")) != evidence["units"]
    ):
        return False
    existing = facts.get("order_reconciliation")
    if isinstance(existing, dict):
        if (
            existing.get("mart_orders") is not None
            and _whole(existing["mart_orders"]) != evidence["orders"]
            or existing.get("mart_units") is not None
            and _whole(existing["mart_units"]) != evidence["units"]
        ):
            return False
    return True


def project_mart_deterministic(
    row: dict[str, Any], evidence: Mapping[str, Any], start: date
) -> bool:
    """Apply both missing dimensions; leave other scores, UI shape and DB untouched."""
    if _eligible(row) is None:
        return False
    facts, evaluation = row["facts"], row["evaluation"]
    if (
        facts.get("first_wfs_available_date_la") not in (None, "")
        and _day(facts.get("first_wfs_available_date_la")) != start
    ):
        return False
    dims = evaluation["dimensions"]
    first = (evidence["first_date"] - start).days + 1
    if not 1 <= first <= 14:
        return False
    score = evaluate(
        {
            "market_score": None,
            "elapsed_days": 14,
            "first_order_day": first,
            "effective_orders_14d": evidence["orders"],
            "valid_orders_14d": evidence["orders"],
            "valid_units_14d": evidence["units"],
            "single_unit_orders_14d": evidence["singles"],
            "ad_status": "unknown",
        },
        {"confirmedScoring": DEFAULT_PARAMETERS, "weights": DEFAULT_WEIGHTS},
        0,
    )
    speed, trust = score["dimensions"].get("speed"), score["dimensions"].get("trust")
    if speed is None or trust is None:
        return False
    # The old V5 view can have both score headers null while the detail pane
    # independently computes their sub-parts. Update the authoritative score
    # fields, not just the sub-part evidence.
    if dims.get("speed") is None:
        dims["speed"] = speed
    if dims.get("trust") is None:
        dims["trust"] = trust
    facts.update(
        {
            "first_wfs_available_date_la": start.isoformat(),
            "first_order_day": first,
            "effective_orders_14d": evidence["orders"],
            "valid_orders_14d": evidence["orders"],
            "valid_units_14d": str(evidence["units"]),
            "single_unit_orders_14d": evidence["singles"],
            "observation_first_order_date_la": evidence["first_date"].isoformat(),
            "order_unit_display_source": "mart_daily_sales_item_day",
            "speed_evidence_source": VERSION,
            "trust_evidence_source": VERSION,
            "data_status": "partial",
        }
    )
    rect = facts.get("order_reconciliation")
    facts["order_reconciliation"] = {
        **(rect if isinstance(rect, dict) else {}),
        "version": VERSION,
        "decision": "MART_DAILY_SINGLE_COUNTS_PROVEN",
        "mart_orders": evidence["orders"],
        "mart_units": str(evidence["units"]),
        "verified_orders": evidence["orders"],
        "verified_units": evidence["units"],
        "verified_singles": evidence["singles"],
    }
    evaluation["total"] = None
    evaluation["grade"] = None
    evaluation["automatic_points"] = str(
        sum(
            (
                Decimal(str(dims[k])) * Decimal(DEFAULT_WEIGHTS[k]) / 100
                for k in ("speed", "ad", "profit", "trust")
                if dims.get(k) is not None
            ),
            Decimal(0),
        )
    )
    evaluation["covered_weight_pct"] = sum(
        DEFAULT_WEIGHTS[k] for k in ("speed", "ad", "profit", "trust") if dims.get(k) is not None
    )
    reasons = evaluation.get("missing")
    if isinstance(reasons, list):
        obsolete = {
            "FACT与MART订单数或销售件数不一致，数据可信度待核实",
            "首次WFS可售日/14天有效订单/首单日",
            "销售件数/订单数/单件订单占比",
        }
        evaluation["missing"] = [r for r in reasons if r not in obsolete]
    if "suggested_qty" in row:
        row["suggested_qty"] = None
    return True


def reconcile_mart_only_pending_rows(session: Any, rows: list[dict[str, Any]]) -> None:
    """One bounded snapshot read + one bounded MART read for local unfrozen page."""
    if os.getenv("APP_ENV", "").strip().lower() not in {"local", "dev", "development"}:
        return
    eligible = {key: row for row in rows if (key := _eligible(row)) is not None}
    if not eligible or len(eligible) > MAX_PAGE:
        return
    wanted = json.dumps([{"account": a, "store": s, "item": i} for a, s, i in eligible])
    try:
        snapshots = {
            _key(m): dict(m) for m in session.execute(_SNAP_SQL, {"wanted": wanted}).mappings()
        }
        windows = []
        for key, row in eligible.items():
            snap = snapshots.get(key)
            if snap is None:
                continue
            start = _day(snap.get("start_day"))
            end = _day(snap.get("end_day"))
            if start is None or end != start + timedelta(days=13) or end >= datetime.now(LA).date():
                continue
            windows.append(
                {
                    "account": key[0],
                    "store": key[1],
                    "item": key[2],
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                }
            )
        if not windows:
            return
        buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        result = list(
            session.execute(
                _MART_SQL, {"windows": json.dumps(windows), "limit": MAX_MART_ROWS + 1}
            ).mappings()
        )
        if len(result) > MAX_MART_ROWS:
            LOG.warning("new_products_mart_only_v5=page_limit_reached")
            return
        for r in result:
            buckets[_key(r)].append(dict(r))
        corrected = 0
        for w in windows:
            key = _key(w)
            snap = snapshots[key]
            start = _day(snap["start_day"])
            evidence = mart_deterministic_evidence(
                start, _day(snap["end_day"]), buckets.get(key, [])
            )
            if evidence is None or not _source_matches(eligible[key], snap, evidence):
                continue
            if project_mart_deterministic(eligible[key], evidence, start):
                corrected += 1
        LOG.info("new_products_mart_only_v5 corrected=%d checked=%d", corrected, len(windows))
    except Exception as exc:
        LOG.warning("new_products_mart_only_v5=read_failed type=%s", type(exc).__name__)
