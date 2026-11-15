"""Read-only V5 view fix for conflicting committed PR337 V4 evidence.

DO NOT mutate score history, persisted JSONB or historical FACT identities.
Only adjusts pending/unfrozen API rows when the V4 saved evidence agrees
with the independent MART snapshot about source totals and its discrepancy.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

MARKER = "PR337_SALESTAT_PERSISTED_VIEW_V5_20261114"
_REASON = "FACT与MART订单数或销售件数不一致，数据可信度待核实"


def _number(x: Any) -> Decimal | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        n = Decimal(str(x))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return n if n.is_finite() and n >= 0 else None


def _natural(x: Any) -> int | None:
    n = _number(x)
    return int(n) if n is not None and n == n.to_integral_value() else None


def _date(x: Any) -> date | None:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return None


def _score_equal(x: Any, y: Any) -> bool:
    a, b = _number(x), _number(y)
    return (
        a is not None and b is not None and a <= 10 and b <= 10 and abs(a - b) <= Decimal("0.015")
    )


def correct_pending_v4_projection(row: dict[str, Any], perf: Any, coverage: Any) -> bool:
    """Return True when a protected, read-only API-view reconciliation applied.

    This never derives single-order distribution from sales totals and never
    promotes non-current order facts. Source consistency must be independently
    recorded in the V4 snapshot, with exact matching windows and metrics.
    """
    if not isinstance(row, dict) or not isinstance(coverage, dict):
        return False
    facts, ev = row.get("facts"), row.get("evaluation")
    if not isinstance(facts, dict) or not isinstance(ev, dict):
        return False
    if ev.get("observation_state") != "automatic_partial":
        return False  # Never alter finalized, approved, frozen or unknown states.
    if _natural(ev.get("rule_version")) != 0:
        return False
    saved = coverage.get("auto_dimension_scores")
    quality = coverage.get("rebuild_quality")
    if not isinstance(saved, dict) or not isinstance(quality, dict):
        return False
    if (
        saved.get("scoring_provenance") != "PR337_SOURCE_REBUILD_V4"
        or _natural(saved.get("rule_version")) != 0
        or quality.get("source_consistency") != "MART_ORDER_FACT_MISMATCH"
        or _natural(quality.get("rule_version")) != 0
    ):
        return False
    start, end = (
        _date(getattr(perf, key, None))
        for key in ("metric_window_start_la", "metric_window_end_la")
    )
    if start is None or end != start + timedelta(days=13):
        return False
    if (
        quality.get("source_date_start_la") != start.isoformat()
        or quality.get("source_date_end_la") != end.isoformat()
    ):
        return False

    mart_orders = _natural(getattr(perf, "sales_orders", None))
    mart_units = _number(getattr(perf, "sales_units", None))
    fact_orders = _natural(quality.get("order_fact_orders"))
    fact_units = _number(quality.get("order_fact_units"))
    if (
        mart_orders is None
        or mart_units is None
        or fact_orders is None
        or fact_units is None
        or _natural(quality.get("mart_orders")) != mart_orders
        or _number(quality.get("mart_units")) != mart_units
        or (fact_orders, fact_units) == (mart_orders, mart_units)
        or fact_orders > 100000000
        or mart_orders > 100000000
    ):
        return False
    score_dimensions = ev.get("dimensions")
    saved_dimensions = saved.get("dimensions")
    if not isinstance(score_dimensions, dict) or not isinstance(saved_dimensions, dict):
        return False
    for kind in ("speed", "trust", "ad", "profit"):
        a, b = score_dimensions.get(kind), saved_dimensions.get(kind)
        if a is None or b is None:
            if a is not None or b is not None:
                return False
        elif not _score_equal(a, b):
            return False

    # If a recorded V4 FACT proof exists, verify its old metrics were actually
    # the ones used in the persisted V4 score, not an unrelated/hijacked row.
    speed_proof = coverage.get("speed_history_full")
    trust_proof = coverage.get("trust_history_full")
    for dim, proof in (("speed", speed_proof), ("trust", trust_proof)):
        if saved_dimensions.get(dim) is None:
            continue
        if (
            not isinstance(proof, dict)
            or proof.get("status") != "scored"
            or proof.get("source") != "fact_walmart_order_items"
            or _natural(proof.get("rule_version")) != 0
            or proof.get("window_start_la") != start.isoformat()
            or proof.get("window_end_la") != end.isoformat()
            or not _score_equal(proof.get("score"), saved_dimensions[dim])
            or _natural(proof.get("mart_orders")) != mart_orders
        ):
            return False
    if saved_dimensions.get("speed") is not None:
        if (
            _natural(speed_proof.get("order_fact_orders")) != fact_orders
            or _natural(speed_proof.get("effective_orders_14d")) != fact_orders
        ):
            return False
    if saved_dimensions.get("trust") is not None:
        if (
            _natural(trust_proof.get("valid_orders_14d")) != fact_orders
            or _number(trust_proof.get("valid_units_14d")) != fact_units
            or _number(trust_proof.get("mart_units")) != mart_units
        ):
            return False

    # Only use first-order-day when the first-date evidence agrees with the
    # persisted observation window and the original V4 proven order-fact day.
    first_day: int | None = None
    if isinstance(speed_proof, dict):
        day = _natural(speed_proof.get("first_order_day"))
        first_order_date = _date(getattr(perf, "first_order_date_la", None))
        if (
            day is not None
            and 1 <= day <= 14
            and first_order_date is not None
            and first_order_date == start + timedelta(days=day - 1)
            and _natural(speed_proof.get("order_fact_orders")) == fact_orders
        ):
            first_day = day

    too_many_fact_orders = fact_orders > mart_orders or fact_units > mart_units
    invalid_lines = _natural(quality.get("invalid_source_lines"))
    source_invalid = invalid_lines is None or invalid_lines > 0
    # Do not mutate row until every provenance check has finished.
    new_orders = None if too_many_fact_orders or source_invalid else mart_orders
    new_speed: str | None = None
    if new_orders is not None and (new_orders == 0 or first_day is not None):
        params = {"confirmedScoring": DEFAULT_PARAMETERS, "weights": DEFAULT_WEIGHTS}
        # Same authoritative scoring engine as V4; no UI-specific score formula.
        computed = evaluate(
            {
                "elapsed_days": 14,
                "first_order_day": first_day,
                "effective_orders_14d": new_orders,
                "ad_status": "unknown",
                "market_score": None,
            },
            params,
            0,
        )
        new_speed = computed["dimensions"].get("speed")

    facts["effective_orders_14d"] = new_orders
    facts["first_order_day"] = first_day if new_orders is not None else None
    # Display the independent MART sales totals as sales facts. They do NOT
    # establish the per-order distribution required for the trust score.
    facts["valid_orders_14d"] = new_orders
    facts["valid_units_14d"] = str(mart_units) if new_orders is not None else None
    facts["single_unit_orders_14d"] = None
    facts["order_unit_display_source"] = (
        "mart_daily_sales_item_day" if new_orders is not None else "unverified_conflict"
    )
    facts["speed_evidence_source"] = (
        "MART_WITH_VERIFIED_FIRST_DAY" if new_speed is not None else "MART_FIRST_DAY_NOT_VERIFIED"
    )
    facts["trust_evidence_source"] = "FACT_MART_DISAGREEMENT_NOT_SCORED"
    facts["data_status"] = "partial"
    facts["order_reconciliation"] = {
        "version": MARKER,
        "mart_orders": mart_orders,
        "mart_units": str(mart_units),
        "current_fact_orders": fact_orders,
        "current_fact_units": str(fact_units),
        "decision": "MART_SPEED_FACT_TRUST_BLOCKED"
        if new_speed is not None
        else "SOURCE_CONFLICT_NOT_SCORED",
    }
    score_dimensions["speed"] = new_speed
    score_dimensions["trust"] = None
    # Do not show a fake complete total or final grade after removing trust.
    ev["total"] = None
    ev["grade"] = None
    existing = ev.get("missing")
    ev["missing"] = (
        [*existing, _REASON]
        if isinstance(existing, list) and _REASON not in existing
        else (existing if isinstance(existing, list) else [_REASON])
    )
    ev["automatic_points"] = str(
        sum(
            (
                (_number(score_dimensions.get(k)) or Decimal(0)) * Decimal(DEFAULT_WEIGHTS[k]) / 100
                for k in ("speed", "ad", "profit", "trust")
            ),
            Decimal(0),
        )
    )
    ev["covered_weight_pct"] = sum(
        DEFAULT_WEIGHTS[k]
        for k in ("speed", "ad", "profit", "trust")
        if score_dimensions.get(k) is not None
    )
    if "suggested_qty" in row:
        row["suggested_qty"] = None
    return True
