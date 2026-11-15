"""Display persisted PR337 source evidence consistently in list and detail.

Never queries source MART, never computes or persists a score during GET.
Operates only on an already authorized Listing identity and its saved row.
"""

from __future__ import annotations

from typing import Any

from .pr337_daily_core import VERSION, natural, numeric, to_date


def saved_daily_view(row: dict[str, Any], matched: tuple | None) -> bool:
    if not matched or not isinstance(row, dict):
        return False
    registry, perf = matched
    if perf is None or not isinstance(getattr(perf, "data_coverage_json", None), dict):
        return False
    if row.get("evaluation", {}).get("observation_state") == "frozen":
        return False
    coverage = perf.data_coverage_json
    block = coverage.get("auto_dimension_scores")
    proof = coverage.get("pr337_daily_verified_v1")
    if not isinstance(block, dict) or not isinstance(proof, dict):
        return False
    if (
        block.get("scoring_provenance") != VERSION
        or proof.get("version") != VERSION
        or not isinstance(block.get("dimensions"), dict)
    ):
        return False
    listing = row.get("listing")
    facts = row.get("facts")
    ev = row.get("evaluation")
    if not all(isinstance(x, dict) for x in (listing, facts, ev)):
        return False
    key = tuple(str(listing.get(k) or "") for k in ("source_account_ref", "store_id", "item_id"))
    if key != (registry.source_account_ref, registry.store_id, registry.item_id):
        return False
    start = to_date(getattr(perf, "metric_window_start_la", None))
    end = to_date(getattr(perf, "metric_window_end_la", None))
    first = to_date(getattr(perf, "first_wfs_available_date_la", None))
    first_order = to_date(getattr(perf, "first_order_date_la", None))
    if (
        start is None
        or first != start
        or end is None
        or proof.get("window_start_la") != start.isoformat()
        or proof.get("window_end_la") != end.isoformat()
        or proof.get("first_order_date") != (first_order.isoformat() if first_order else None)
        or natural(getattr(perf, "sales_orders", None)) != natural(proof.get("orders"))
        or numeric(getattr(perf, "sales_units", None)) != numeric(proof.get("units"))
    ):
        return False
    values = block["dimensions"]
    if not all(
        (v is None or (numeric(v) is not None and 0 <= numeric(v) <= 10))
        for k, v in values.items()
        if k in ("speed", "ad", "profit", "trust")
    ):
        return False
    # The persisted dimension is the authority; no Order V2 backfill on GET.
    for k in ("speed", "ad", "profit", "trust"):
        ev["dimensions"][k] = str(values.get(k)) if values.get(k) is not None else None
    ev["rule_version"] = block.get("rule_version", 0)
    ev["observation_state"] = "automatic_partial"
    ev["total"] = str(perf.score) if perf.score is not None else None
    ev["grade"] = perf.grade
    ev["missing"] = [k for k, v in ev["dimensions"].items() if v is None]
    ev["automatic_points"] = block.get("automatic_points")
    ev["covered_weight_pct"] = block.get("covered_weight_pct")
    facts.update(
        {
            "first_wfs_available_date_la": proof["window_start_la"],
            "first_order_day": proof.get("first_order_day"),
            "first_order_date": proof.get("first_order_date"),
            "effective_orders_14d": natural(proof.get("orders")),
            "sales_orders": natural(proof.get("orders")),
            "sales_units": str(proof["units"]),
            "sales_amount_usd": str(perf.sales_amount_usd)
            if perf.sales_amount_usd is not None
            else None,
            "profit_usd": str(perf.profit_usd) if perf.profit_usd is not None else None,
            "roi": str(perf.roi) if perf.roi is not None else None,
            "gross_margin_pct": str(perf.profit_margin_pct)
            if perf.profit_margin_pct is not None
            else None,
            "ad_spend_usd": str(perf.ad_spend_usd) if perf.ad_spend_usd is not None else None,
            "ad_clicks": perf.ad_clicks,
            "ad_revenue_usd": str(perf.ad_sales_usd) if perf.ad_sales_usd is not None else None,
            "valid_orders_14d": natural(proof.get("orders")),
            "valid_units_14d": str(proof["units"]),
            "single_unit_orders_14d": natural(proof.get("singles"))
            if proof.get("trust_proven")
            else None,
            "speed_evidence_source": VERSION,
            "trust_evidence_source": VERSION if proof.get("trust_proven") else "UNVERIFIED_SINGLES",
            "order_unit_display_source": "mart_daily_sales_item_day",
            "data_cutoff_la": proof["cutoff_la"],
            "metric_window_start_la": proof["window_start_la"],
            "metric_window_end_la": proof["window_end_la"],
            "observation_complete": proof.get("observation_complete"),
            "data_status": perf.data_status or "partial",
        }
    )
    return True
