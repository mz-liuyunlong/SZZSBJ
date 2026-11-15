"""Opt-in post-publication trust evidence synchronizer for saved PR337 scores.

This never recomputes or overwrites a published score, grade or prior proof.
It is deliberately absent from GET /listings. A new 0088 JSONB key is used;
there are no schema changes. Historical rows before the deployment gate are excluded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .rules import DEFAULT_PARAMETERS, dec
from .scoring import clamp, up, weighted

_BATCH_LIMIT = 50
_TOLERANCE = Decimal("0.00501")

# Candidate snapshots and the order records are read in bounded, set-based queries.
# The LEFT JOIN to tracking prevents modification of final outcomes.
_CANDIDATES = text("""
SELECT p.registry_id::text AS registry_id,
       r.source_account_ref AS account, r.store_id AS store, r.item_id AS item,
       p.first_wfs_available_date_la AS first_wfs,
       p.metric_window_start_la AS start_day,
       p.metric_window_end_la AS end_day,
       p.sales_units AS saved_units, p.sales_orders AS saved_orders,
       p.calculated_at, p.calculated_at::text AS calculated_marker,
       p.rule_version_id::text AS rule_version_id,
       rv.version AS active_version, rv.config_json AS rule_config,
       p.data_coverage_json AS coverage
FROM biz_new_product_performance_current p
JOIN biz_new_product_registry r ON r.id=p.registry_id
LEFT JOIN biz_new_product_rule_versions rv ON rv.id=p.rule_version_id
LEFT JOIN biz_new_product_tracking_current t ON t.registry_id=p.registry_id
WHERE p.calculated_at >= :after_date
  AND p.data_coverage_json #>> '{auto_dimension_scores,dimensions,trust}' IS NOT NULL
  AND (p.data_coverage_json->'trust_history_full' IS NULL
       OR (p.data_coverage_json #>> '{trust_history_full,provenance}'
             = 'post_publication_order_fact_verification_v1'
           AND p.data_coverage_json #>> '{trust_history_full,calculated_marker}'
                IS DISTINCT FROM p.calculated_at::text))
  AND p.data_coverage_json->'trust_evidence_v1' IS NULL
  AND CASE
    WHEN p.data_coverage_json->'trust_evidence_history' IS NULL THEN TRUE
    WHEN jsonb_typeof(p.data_coverage_json->'trust_evidence_history')='array'
      THEN jsonb_array_length(p.data_coverage_json->'trust_evidence_history') < 30
    ELSE FALSE END
  AND p.score IS NULL AND p.grade IS NULL
  AND t.final_result IS NULL
  AND (p.process_status IS NULL OR p.process_status NOT IN ('打品成功','打品失败','成功','失败'))
  AND NOT EXISTS (
    SELECT 1 FROM biz_new_product_tracking_decisions d
    WHERE d.source_account_ref=r.source_account_ref AND d.store_id=r.store_id
      AND d.item_id=r.item_id AND d.decision IN ('打品成功','打品失败')
  )
  AND NOT EXISTS (
    SELECT 1 FROM biz_new_product_tracking_review_applications a
    WHERE a.registry_id=p.registry_id AND a.status='approved'
      AND a.proposed_result IN ('打品成功','打品失败')
  )
ORDER BY p.calculated_at, p.registry_id
LIMIT :batch_limit
""")

# Use the same identity, order grouping, sampling and cancellation predicates as
# app.modules.new_products.bulk_read._ORDERS_SQL. Unknown/invalid fact lines
# must fail validation instead of silently becoming zero/valid orders.
_ORDERS = text("""
WITH wanted AS (
  SELECT registry_id, account, store, item, start_day, end_day
  FROM jsonb_to_recordset(CAST(:wanted AS jsonb)) AS j(
    registry_id uuid, account text, store text, item text,
    start_day date, end_day date)
), grouped AS (
  SELECT w.registry_id, f.source_order_id AS order_ref,
         SUM(f.quantity) AS units,
         COUNT(*) FILTER (WHERE f.source_order_id IS NULL OR f.quantity IS NULL
           OR f.quantity<=0 OR f.quantity<>TRUNC(f.quantity)
           OR f.business_date_la IS NULL) AS invalid_lines
  FROM wanted w JOIN fact_walmart_order_items f
    ON f.source_account_ref=w.account AND f.store_id=w.store AND f.item_id=w.item
  WHERE f.is_identity_current IS TRUE
    AND f.is_sample_order IS FALSE
    AND f.business_date_la BETWEEN w.start_day AND w.end_day
    AND upper(COALESCE(f.order_status_raw,'')) NOT IN ('CANCELED','CANCELLED','CANCEL','VOID')
  GROUP BY w.registry_id, f.source_order_id
)
SELECT registry_id::text AS registry_id,
       COUNT(*) AS orders, COALESCE(SUM(units),0) AS units,
       COUNT(*) FILTER (WHERE units=1 AND invalid_lines=0) AS singles,
       COALESCE(SUM(invalid_lines),0) AS invalid_lines,
       COUNT(*) FILTER (WHERE order_ref IS NULL) AS missing_refs
FROM grouped GROUP BY registry_id
""")

_UPDATE = text("""
UPDATE biz_new_product_performance_current p
SET data_coverage_json = jsonb_set(
    CASE WHEN p.data_coverage_json->'trust_history_full' IS NOT NULL
         THEN jsonb_set(p.data_coverage_json, '{trust_evidence_history}',
           COALESCE(p.data_coverage_json->'trust_evidence_history','[]'::jsonb)
           || jsonb_build_array(p.data_coverage_json->'trust_history_full'), true)
         ELSE p.data_coverage_json END,
    '{trust_history_full}',CAST(:proof AS jsonb),true)
WHERE p.registry_id=CAST(:registry_id AS uuid)
  AND p.calculated_at=:calculated_at
  AND p.metric_window_start_la=:start_day
  AND p.metric_window_end_la=:end_day
  AND p.sales_units=:saved_units AND p.sales_orders=:saved_orders
  AND p.rule_version_id IS NOT DISTINCT FROM CAST(:rule_version_id AS uuid)
  AND p.data_coverage_json IS NOT DISTINCT FROM CAST(:old_coverage AS jsonb)
  AND (p.data_coverage_json->'trust_history_full' IS NULL
       OR (p.data_coverage_json #>> '{trust_history_full,provenance}'
             = 'post_publication_order_fact_verification_v1'
           AND p.data_coverage_json #>> '{trust_history_full,calculated_marker}'
                IS DISTINCT FROM p.calculated_at::text))
  AND p.data_coverage_json->'trust_evidence_v1' IS NULL
  AND CASE
    WHEN p.data_coverage_json->'trust_evidence_history' IS NULL THEN TRUE
    WHEN jsonb_typeof(p.data_coverage_json->'trust_evidence_history')='array'
      THEN jsonb_array_length(p.data_coverage_json->'trust_evidence_history') < 30
    ELSE FALSE END
  AND p.score IS NULL AND p.grade IS NULL
  AND (p.process_status IS NULL OR p.process_status NOT IN ('打品成功','打品失败','成功','失败'))
  AND NOT EXISTS (SELECT 1 FROM biz_new_product_tracking_current t
                  WHERE t.registry_id=p.registry_id AND t.final_result IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM biz_new_product_registry r
    JOIN biz_new_product_tracking_decisions d
    ON d.source_account_ref=r.source_account_ref AND d.store_id=r.store_id
       AND d.item_id=r.item_id
    WHERE r.id=p.registry_id AND d.decision IN ('打品成功','打品失败'))
  AND NOT EXISTS (SELECT 1 FROM biz_new_product_tracking_review_applications a
    WHERE a.registry_id=p.registry_id AND a.status='approved'
      AND a.proposed_result IN ('打品成功','打品失败'))
""")


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _nonnegative_int(value: Any) -> int | None:
    n = _decimal(value)
    if n is None or n < 0 or n != n.to_integral_value():
        return None
    return int(n)


def _trust_params(row: dict[str, Any]) -> tuple[dict[str, Any], int] | None:
    coverage = row.get("coverage")
    if not isinstance(coverage, dict):
        return None
    auto = coverage.get("auto_dimension_scores")
    if not isinstance(auto, dict) or not isinstance(auto.get("dimensions"), dict):
        return None
    if row.get("rule_version_id") is None:
        if auto.get("rule_version", 0) not in (None, 0, "0"):
            return None
        return DEFAULT_PARAMETERS["trust"], 0
    version = _nonnegative_int(row.get("active_version"))
    config = row.get("rule_config")
    if version is None or version < 1 or auto.get("rule_version") not in (version, str(version)):
        return None
    try:
        return config["confirmedScoring"]["trust"], version
    except (KeyError, TypeError):
        return None


def _valid_window(row: dict[str, Any]) -> bool:
    start = row.get("start_day")
    end = row.get("end_day")
    first = row.get("first_wfs")
    return (
        isinstance(start, date) and isinstance(end, date) and isinstance(first, date)
        and first <= start <= end and 0 <= (end - first).days <= 13
    )


def trust_score(*, units: Decimal, orders: int, singles: int, params: dict[str, Any]) -> Decimal:
    """Exactly the trust part of scoring.evaluate; do not round intermediate values."""
    return weighted([
        (clamp(units / dec(params["targetUnits"]) * 10), dec(params["unitsWeight"])),
        (up(Decimal(singles) / Decimal(orders) * 100,
            dec(params["singleRatioZero"]), dec(params["singleRatioFull"])),
         dec(params["singleRatioWeight"])),
    ])


def verified_evidence(row: dict[str, Any], origin: dict[str, Any] | None) -> dict[str, Any] | None:
    """Fail closed for mixed source versions, unknown quantities and score drift."""
    if origin is None or not _valid_window(row):
        return None
    coverage = row.get("coverage")
    if not isinstance(coverage, dict):
        return None
    auto = coverage.get("auto_dimension_scores", {})
    if not isinstance(auto, dict) or not isinstance(auto.get("dimensions"), dict):
        return None
    saved_score = _decimal(auto["dimensions"].get("trust"))
    saved_units = _decimal(row.get("saved_units"))
    saved_orders = _nonnegative_int(row.get("saved_orders"))
    actual_units = _decimal(origin.get("units"))
    actual_orders = _nonnegative_int(origin.get("orders"))
    singles = _nonnegative_int(origin.get("singles"))
    invalid = _nonnegative_int(origin.get("invalid_lines"))
    missing = _nonnegative_int(origin.get("missing_refs"))
    if (
        saved_score is None or saved_score < 0 or saved_score > 10
        or saved_units is None or saved_orders is None or saved_orders <= 0
        or actual_units is None or actual_orders is None or singles is None
        or invalid != 0 or missing != 0 or actual_orders <= 0
        or actual_units != saved_units or actual_orders != saved_orders
        or actual_units < actual_orders or singles > actual_orders
    ):
        return None
    resolved = _trust_params(row)
    if resolved is None:
        return None
    params, version = resolved
    try:
        check_score = trust_score(units=actual_units, orders=actual_orders,
                                  singles=singles, params=params)
    except (ValueError, InvalidOperation, ZeroDivisionError, KeyError, TypeError):
        return None
    if abs(check_score - saved_score) > _TOLERANCE:
        return None
    return {
        "source": "fact_walmart_order_items",
        "status": "scored",
        "window_start_la": row["start_day"].isoformat(),
        "window_end_la": row["end_day"].isoformat(),
        "valid_units_14d": str(actual_units),
        "valid_orders_14d": actual_orders,
        "single_unit_orders_14d": singles,
        "saved_trust_score": str(saved_score),
        "verified_trust_score": str(check_score),
        "rule_version": version,
        "verified_match": "MATCH",
        "calculated_marker": row["calculated_marker"],
        "provenance": "post_publication_order_fact_verification_v1",
    }


def _wanted(rows: list[dict[str, Any]]) -> str:
    return json.dumps([{
        "registry_id": r["registry_id"], "account": r["account"],
        "store": r["store"], "item": r["item"],
        "start_day": r["start_day"].isoformat(),
        "end_day": r["end_day"].isoformat(),
    } for r in rows], separators=(",", ":"))


@dataclass(frozen=True)
class SyncResult:
    examined: int = 0
    verified: int = 0
    written: int = 0
    skipped: int = 0
    disabled: bool = False
    locked: bool = False


def sync_saved_trust_evidence(
    session: Session, *, after_date: datetime, dry_run: bool = False,
    batch_limit: int = _BATCH_LIMIT,
) -> SyncResult:
    """One bounded transaction; only appends proof to JSONB. No historical rewrites.

    Caller must explicitly authorize production DB writes. A deployment-date
    lower bound excludes the existing 77 proven and 11 unreconciled rows.
    """
    if after_date.tzinfo is None or after_date.utcoffset() is None:
        raise ValueError("after_date must be timezone aware")
    if not 1 <= batch_limit <= _BATCH_LIMIT:
        raise ValueError("batch_limit must be in [1, 50]")
    session.execute(text("SET LOCAL lock_timeout = '3s'"))
    session.execute(text("SET LOCAL statement_timeout = '90s'"))
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(337, 20261114)")):
        return SyncResult(locked=True)

    rows = [dict(r) for r in session.execute(_CANDIDATES, {
        "after_date": after_date.astimezone(UTC), "batch_limit": batch_limit,
    }).mappings().all()]
    eligible = [r for r in rows if _valid_window(r)]
    if not eligible:
        return SyncResult(examined=len(rows), skipped=len(rows))
    order_rows = {
        r["registry_id"]: dict(r)
        for r in session.execute(_ORDERS, {"wanted": _wanted(eligible)}).mappings()
    }
    verified = 0
    written = 0
    for r in eligible:
        proof = verified_evidence(r, order_rows.get(r["registry_id"]))
        if proof is None:
            continue
        verified += 1
        if dry_run:
            continue
        updated = session.execute(_UPDATE, {
            "registry_id": r["registry_id"],
            "calculated_at": r["calculated_at"],
            "start_day": r["start_day"], "end_day": r["end_day"],
            "saved_units": r["saved_units"], "saved_orders": r["saved_orders"],
            "rule_version_id": r["rule_version_id"],
            "old_coverage": json.dumps(r["coverage"], separators=(",", ":")),
            "proof": json.dumps(proof, separators=(",", ":")),
        })
        if updated.rowcount != 1:
            raise RuntimeError("TRUST_EVIDENCE_CONCURRENT_UPDATE: rollback whole batch")
        written += 1
    return SyncResult(examined=len(rows), verified=verified,
                      written=written, skipped=len(rows) - verified)
