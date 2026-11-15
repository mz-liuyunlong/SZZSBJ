"""Local-only read-view overlay from independently reviewed SQL reconciliations.

The helper does not query or write a database. Its evidence manifest is not a
replacement for a maintained canonical order-fact pipeline. It only returns
scores for an exactly matched, unfrozen, previously reconciled V5 snapshot.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

MARKER = "PR337_SQL_ATTESTED_CURRENT_VIEW_V6_20261114"
_EVIDENCE_FILE = Path(__file__).with_name("v6_sql_attestations.json")
_V5_REASON = "FACT与MART订单数或销售件数不一致，数据可信度待核实"


def _num(x: Any) -> Decimal | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        n = Decimal(str(x))
    except (ValueError, InvalidOperation, TypeError):
        return None
    return n if n.is_finite() and n >= 0 else None


def _natural(x: Any) -> int | None:
    n = _num(x)
    return int(n) if n is not None and n == n.to_integral_value() else None


def _date(x: Any) -> date | None:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return None


def _iso(x: Any) -> date | None:
    if not isinstance(x, str):
        return None
    try:
        d = date.fromisoformat(x)
    except ValueError:
        return None
    return d


def _proof_list() -> list[dict[str, Any]]:
    # The packaged file is an independently reviewed, dated read-only SQL result.
    # Empty / bad / overwritten evidence must fail closed, not fabricate scores.
    try:
        proof = json.loads(_EVIDENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return (
        proof.get("reconciliations", [])
        if isinstance(proof, dict) and isinstance(proof.get("reconciliations"), list)
        else []
    )


def apply_attested_current_view(
    row: dict[str, Any],
    perf: Any,
    coverage: Any,
    *,
    attestations: list[dict[str, Any]] | None = None,
) -> bool:
    """Project verified scores without modifying persisted data; never freeze/unfreeze."""
    if os.getenv("APP_ENV", "").strip().lower() not in {"local", "dev", "development"}:
        return False
    if not isinstance(row, dict) or not isinstance(coverage, dict):
        return False
    listing, facts, evaluation = row.get("listing"), row.get("facts"), row.get("evaluation")
    if not all(isinstance(x, dict) for x in (listing, facts, evaluation)):
        return False
    if (
        evaluation.get("observation_state") != "automatic_partial"
        or _natural(evaluation.get("rule_version")) != 0
    ):
        return False
    rect = facts.get("order_reconciliation")
    if (
        not isinstance(rect, dict)
        or rect.get("version") != "PR337_SALESTAT_PERSISTED_VIEW_V5_20261114"
    ):
        return False
    if _natural(rect.get("mart_orders")) != _natural(facts.get("effective_orders_14d")):
        return False
    if _num(rect.get("mart_units")) != _num(facts.get("valid_units_14d")):
        return False
    if evaluation.get("dimensions", {}).get("trust") is not None:
        return False  # Do not overwrite an already scored/verified trust dimension.
    saved, quality = coverage.get("auto_dimension_scores"), coverage.get("rebuild_quality")
    if not isinstance(saved, dict) or not isinstance(quality, dict):
        return False
    if (
        saved.get("scoring_provenance") != "PR337_SOURCE_REBUILD_V4"
        or _natural(saved.get("rule_version")) != 0
        or quality.get("source_consistency") != "MART_ORDER_FACT_MISMATCH"
        or _natural(quality.get("rule_version")) != 0
        or _natural(quality.get("invalid_source_lines")) != 0
    ):
        return False
    start, end = (
        _date(getattr(perf, "metric_window_start_la", None)),
        _date(getattr(perf, "metric_window_end_la", None)),
    )
    first = _date(getattr(perf, "first_order_date_la", None))
    if start is None or end != start + timedelta(days=13) or first is None:
        return False
    if (
        quality.get("source_date_start_la") != start.isoformat()
        or quality.get("source_date_end_la") != end.isoformat()
    ):
        return False
    candidates = attestations if attestations is not None else _proof_list()
    # No unspecified stores, accounts or items can receive inferred scores.
    matched = [
        p
        for p in candidates
        if isinstance(p, dict)
        and p.get("store_id") == listing.get("store_id")
        and p.get("item_id") == listing.get("item_id")
        and p.get("start_date") == start.isoformat()
        and p.get("end_date") == end.isoformat()
    ]
    if len(matched) != 1:
        return False
    proof = matched[0]
    if proof.get("verification") != "SQL_READ_ONLY_REVIEWED_NO_AMBIGUITY":
        return False
    if (
        proof.get("mart_first") != first.isoformat()
        or proof.get("saved_first") != first.isoformat()
        or proof.get("fact_first") is None
        or proof.get("historical_first") is None
    ):
        return False
    cf, hf = _iso(proof.get("fact_first")), _iso(proof.get("historical_first"))
    if (
        cf is None
        or hf is None
        or min(cf, hf) != first
        or not start <= cf <= end
        or not start <= hf <= end
    ):
        return False
    days = (first - start).days + 1
    if not 1 <= days <= 14:
        return False
    # Compare supplied attestation to both immutable V4 coverage and V5 view,
    # so a different version, identity or snapshot cannot inherit this score.
    current_orders = _natural(proof.get("current_orders"))
    current_units = _num(proof.get("current_units"))
    current_singles = _natural(proof.get("current_singles"))
    old_orders = _natural(quality.get("order_fact_orders"))
    old_units = _num(quality.get("order_fact_units"))
    orders = _natural(proof.get("mart_orders"))
    units = _num(proof.get("mart_units"))
    hist_orders = _natural(proof.get("historical_orders"))
    hist_units = _num(proof.get("historical_units"))
    hist_singles = _natural(proof.get("historical_singles"))
    if any(
        x is None
        for x in (
            current_orders,
            current_units,
            current_singles,
            old_orders,
            old_units,
            orders,
            units,
            hist_orders,
            hist_units,
            hist_singles,
        )
    ):
        return False
    if (
        current_orders != old_orders
        or current_units != old_units
        or _natural(quality.get("mart_orders")) != orders
        or _num(quality.get("mart_units")) != units
        or _natural(getattr(perf, "sales_orders", None)) != orders
        or _num(getattr(perf, "sales_units", None)) != units
        or _natural(rect.get("current_fact_orders")) != current_orders
        or _num(rect.get("current_fact_units")) != current_units
        or _natural(facts.get("effective_orders_14d")) != orders
        or _natural(facts.get("valid_orders_14d")) != orders
        or _num(facts.get("valid_units_14d")) != units
        or _natural(proof.get("ambiguous_orders")) != 0
    ):
        return False
    if (
        orders <= 0
        or current_orders + hist_orders != orders
        or current_units + hist_units != units
        or current_singles > current_orders
        or hist_singles > hist_orders
        or units < orders
    ):
        return False
    if facts.get("first_order_day") not in (None, days):
        return False
    trust_history = coverage.get("trust_history_full")
    if (
        not isinstance(trust_history, dict)
        or trust_history.get("source") != "fact_walmart_order_items"
    ):
        return False
    if (
        trust_history.get("status") != "scored"
        or _natural(trust_history.get("rule_version")) != 0
        or _natural(trust_history.get("valid_orders_14d")) != current_orders
        or _num(trust_history.get("valid_units_14d")) != current_units
        or _natural(trust_history.get("single_unit_orders_14d")) != current_singles
    ):
        return False
    # V4's old 7.30 remains frozen in coverage but is superseded in API display.
    singles = current_singles + hist_singles
    if singles > orders or singles < 0:
        return False
    result = evaluate(
        {
            "market_score": None,
            "elapsed_days": 14,
            "first_order_day": days,
            "effective_orders_14d": orders,
            "valid_units_14d": units,
            "valid_orders_14d": orders,
            "single_unit_orders_14d": singles,
            "ad_status": "unknown",
        },
        {"confirmedScoring": DEFAULT_PARAMETERS, "weights": DEFAULT_WEIGHTS},
        0,
    )
    speed, trust = result["dimensions"].get("speed"), result["dimensions"].get("trust")
    if speed is None or trust is None:
        return False
    # Only after all checks are complete change the in-memory view; persist NOTHING.
    dims = evaluation["dimensions"]
    dims["speed"] = speed
    dims["trust"] = trust
    facts["first_order_day"] = days
    facts["single_unit_orders_14d"] = singles
    facts["speed_evidence_source"] = "SQL_ATTESTED_SAVED_FIRST_MART_20261114"
    facts["trust_evidence_source"] = "SQL_ATTESTED_RECONCILED_HISTORICAL_20261114"
    facts["order_reconciliation"] = {
        **rect,
        "decision": "ATTESTED_MATCH_NO_AMBIGUITY",
        "version": MARKER,
        "historical_orders": hist_orders,
        "historical_units": str(hist_units),
        "historical_singles": hist_singles,
        "total_singles": singles,
        "verified_at": proof.get("verified_at"),
    }
    missing = evaluation.get("missing")
    if isinstance(missing, list):
        evaluation["missing"] = [x for x in missing if x != _V5_REASON]
    evaluation["automatic_points"] = str(
        sum(
            (_num(dims.get(k)) or Decimal(0)) * Decimal(DEFAULT_WEIGHTS[k]) / 100
            for k in ("speed", "ad", "profit", "trust")
        )
    )
    evaluation["covered_weight_pct"] = sum(
        DEFAULT_WEIGHTS[k] for k in ("speed", "ad", "profit", "trust") if dims.get(k) is not None
    )
    # V5 intentionally suppresses the historical total/grade; leave them unset.
    evaluation["total"] = None
    evaluation["grade"] = None
    return True
