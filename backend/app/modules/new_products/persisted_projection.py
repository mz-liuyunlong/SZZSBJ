"""Scoped, read-only projection of persisted PR337 performance snapshots.

Existing source-account scoping happens in NewProductRepository.page().  This
module queries *only* identities on that scoped page and never recalculates
scores or changes the operational database.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .models import NewProductPerformanceCurrent, NewProductRegistry

Key = tuple[str, str, str]
DIMENSIONS = ("speed", "ad", "profit", "trust")


def load_persisted_page(
    session: Session, identities: Iterable[Key]
) -> dict[Key, tuple[NewProductRegistry, NewProductPerformanceCurrent | None]]:
    keys = list(dict.fromkeys(identities))
    if not keys:
        return {}
    if len(keys) > 200:
        raise ValueError("New-product persisted page exceeds 200 identities")
    registry = NewProductRegistry
    perf = NewProductPerformanceCurrent
    statement = (
        select(registry, perf)
        .outerjoin(perf, perf.registry_id == registry.id)
        .where(tuple_(registry.source_account_ref, registry.store_id, registry.item_id).in_(keys))
    )
    return {
        (r.source_account_ref, r.store_id, r.item_id): (r, p)
        for r, p in session.execute(statement).all()
    }


def _decimal(value: Any, max_value: Decimal | None = None) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None
    if not number.is_finite():
        return None
    if max_value is not None and not (0 <= number <= max_value):
        return None
    return str(number)


def _day(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def _stamp(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


# PR337_PERSISTED_FACT_EVIDENCE_V6: saved evidence only. Never query source facts in GET.
def _evidence_decimal(value: Any) -> Decimal | None:
    encoded = _decimal(value)
    return Decimal(encoded) if encoded is not None else None


def _evidence_valid_integer(value: Any) -> int | None:
    n = _evidence_decimal(value)
    if n is None or n < 0 or n != n.to_integral_value():
        return None
    return int(n)


def _matches_saved_dimension(raw: Any, saved: Any) -> bool:
    actual = _evidence_decimal(raw)
    expected = _evidence_decimal(saved)
    return bool(
        actual is not None
        and expected is not None
        and Decimal(0) <= actual <= Decimal(10)
        and Decimal(0) <= expected <= Decimal(10)
        and abs(actual - expected) <= Decimal("0.015")
    )


def _attach_saved_dimension_evidence(
    row: dict[str, Any], perf: NewProductPerformanceCurrent, coverage: dict[str, Any]
) -> None:
    """Display only facts already saved with the score; never query FDW here.

    The 2026-11-11 historical SP snapshot is cumulative, so do not silently
    present it as the initial 14-day observation window. Check its own saved
    ad score before associating it with an existing dimension score.
    """
    if row.get("evaluation", {}).get("observation_state") == "frozen":
        return
    dimensions = row.get("evaluation", {}).get("dimensions", {})
    if not isinstance(dimensions, dict):
        return
    facts = row.get("facts")
    if not isinstance(facts, dict):
        return

    history = coverage.get("ad_history_full")
    if isinstance(history, dict) and history.get("status") == "scored":
        spend = _evidence_decimal(history.get("spend_usd"))
        sales = _evidence_decimal(history.get("attributed_sales_reported"))
        clicks = _evidence_valid_integer(history.get("clicks"))
        orders = _evidence_valid_integer(history.get("attributed_orders"))
        rows = _evidence_valid_integer(history.get("ad_rows"))
        invalid_core = _evidence_valid_integer(history.get("core_incomplete_rows"))
        invalid_currency = _evidence_valid_integer(history.get("unverified_sales_rows"))
        if (
            history.get("source") == "fact_walmart_ad_item_sp_daily"
            and _matches_saved_dimension(history.get("ad_score"), dimensions.get("ad"))
            and rows is not None
            and rows > 0
            and invalid_core == 0
            and invalid_currency == 0
            and spend is not None
            and spend > 0
            and clicks is not None
            and clicks > 0
            and sales is not None
            and sales >= 0
            and orders is not None
            and orders <= clicks
            and ((orders == 0 and sales == 0) or (orders > 0 and sales > 0))
            and isinstance(history.get("cutoff_la"), str)
        ):
            # Override obsolete fields using the exact saved scoring snapshot.
            facts.update(
                {
                    "ad_status": "active",
                    "ad_spend_usd": str(spend),
                    "ad_clicks": clicks,
                    "ad_orders": orders,
                    "ad_revenue_usd": str(sales),
                    "ad_evidence_cutoff_la": history["cutoff_la"],
                    "ad_evidence_source": "saved_ad_history_full",
                }
            )

    # A saved, explicit single-order count takes precedence over any inference.
    trust = coverage.get("trust_history_full")
    if not isinstance(trust, dict):
        trust = coverage.get("trust_evidence_v1")
    if isinstance(trust, dict) and trust.get("status") == "scored":
        units = _evidence_decimal(trust.get("valid_units_14d"))
        orders = _evidence_valid_integer(trust.get("valid_orders_14d"))
        singles = _evidence_valid_integer(trust.get("single_unit_orders_14d"))
        if (
            trust.get("source") == "fact_walmart_order_items"
            and units is not None
            and units >= 0
            and orders is not None
            and orders > 0
            and singles is not None
            and singles <= orders
            and units >= orders
            and _evidence_decimal(perf.sales_units) == units
            and _evidence_valid_integer(perf.sales_orders) == orders
        ):
            facts["single_unit_orders_14d"] = singles
            facts["single_unit_orders_evidence"] = "saved_order_fact_snapshot"
            return

    # Narrow mathematical identity: when the SAME stored 14-day window has
    # N positive units across N positive orders, every order contains 1 unit.
    # Only accept default rule version and a matching saved trust score. This
    # derives from two persisted measurements, NEVER from the trust score.
    if row.get("evaluation", {}).get("rule_version") != 0:
        return
    units = _evidence_decimal(perf.sales_units)
    orders = _evidence_valid_integer(perf.sales_orders)
    begin = getattr(perf, "metric_window_start_la", None)
    end = perf.metric_window_end_la
    first = perf.first_wfs_available_date_la
    if (
        units is None
        or orders is None
        or orders < 1
        or units != orders
        or not isinstance(begin, date)
        or not isinstance(end, date)
        or not isinstance(first, date)
        or not (first <= begin <= end and end.toordinal() - first.toordinal() <= 13)
    ):
        return
    # Uses the documented default trust weighting, without rescore or write.
    from .rules import DEFAULT_PARAMETERS

    p = DEFAULT_PARAMETERS["trust"]
    unit_component = min(Decimal(10), units / Decimal(str(p["targetUnits"])) * 10)
    ratio_zero = Decimal(str(p["singleRatioZero"]))
    ratio_full = Decimal(str(p["singleRatioFull"]))
    if ratio_full <= ratio_zero:
        return
    ratio_component = max(
        Decimal(0), min(Decimal(10), (Decimal(100) - ratio_zero) * 10 / (ratio_full - ratio_zero))
    )
    proof_score = (
        unit_component * Decimal(str(p["unitsWeight"]))
        + ratio_component * Decimal(str(p["singleRatioWeight"]))
    ) / 100
    if _matches_saved_dimension(proof_score, dimensions.get("trust")):
        facts["single_unit_orders_14d"] = orders
        facts["single_unit_orders_evidence"] = "derived_from_equal_saved_units_and_orders"


def merge_persisted_page_row(
    row: dict[str, Any],
    matched: tuple[NewProductRegistry, NewProductPerformanceCurrent | None] | None,
    today_la: date,
) -> None:
    """Enrich the existing API response in place, without changing its layout contract."""
    # Preserve finalized display exactly as captured at approval.
    if row.get("evaluation", {}).get("observation_state") == "frozen":
        return
    if matched is None or row.get("evaluation", {}).get("observation_state") == "frozen":
        return
    registry, perf = matched
    listing = row["listing"]
    listing["category_l1"] = registry.category_l1
    listing["category_l2"] = registry.category_l2
    if registry.listing_date_la and not listing.get("launch_date_cn"):
        listing["launch_date_cn"] = _day(registry.listing_date_la)
    if perf is None:
        return
    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    category = coverage.get("listing_category")
    if isinstance(category, dict):
        path = category.get("full_path")
        leaf = category.get("leaf")
        if isinstance(path, str) and path.strip():
            listing["category_path"] = path
            if not (isinstance(leaf, str) and leaf.strip()):
                leaf = path.split(" > ")[-1]
        if isinstance(leaf, str) and leaf.strip():
            listing["category"] = leaf.strip()

    facts = row["facts"]
    if perf.first_wfs_available_date_la:
        first = perf.first_wfs_available_date_la
        facts["first_wfs_available_date_la"] = _day(first)
        facts["elapsed_days"] = (today_la - first).days + 1 if first <= today_la else None
        listing["first_wfs_available_date_la"] = _day(first)
    if perf.first_order_date_la:
        facts["first_order_date"] = _day(perf.first_order_date_la)

    # Persisted metrics preserve NULL; NULL must never become 0 or an invented order count.
    for target, attribute in (
        ("valid_orders_14d", "sales_orders"),
        ("effective_orders_14d", "sales_orders"),
        ("valid_units_14d", "sales_units"),
        ("sales_amount_usd", "sales_amount_usd"),
        ("ad_spend_usd", "ad_spend_usd"),
        ("ad_clicks", "ad_clicks"),
        ("ad_revenue_usd", "ad_sales_usd"),
        ("roi", "roi"),
        ("gross_margin_pct", "profit_margin_pct"),
        ("profit_usd", "profit_usd"),
        ("return_rate_units_pct", "return_rate_units_pct"),
        ("return_rate_orders_pct", "return_rate_orders_pct"),
    ):
        raw = getattr(perf, attribute)
        facts[target] = _decimal(raw) if isinstance(raw, Decimal) else raw
    facts["data_cutoff_la"] = _day(perf.metric_window_end_la)
    facts["calculated_at"] = _stamp(perf.calculated_at)
    facts["data_status"] = perf.data_status or (
        "partial" if perf.calculated_at is not None else "not_calculated"
    )

    block = coverage.get("auto_dimension_scores")
    if not isinstance(block, dict):
        return
    original_dims = block.get("dimensions")
    if not isinstance(original_dims, dict):
        return
    dimensions = row["evaluation"]["dimensions"]
    for dim in DIMENSIONS:
        dimensions[dim] = _decimal(original_dims.get(dim), Decimal("10"))
    # Note: market is a human-entered dimension and is never populated here.
    calculated = any(dimensions[dim] is not None for dim in DIMENSIONS)
    if calculated:
        row["evaluation"]["observation_state"] = "automatic_partial"
        row["evaluation"]["missing"] = []
    elif perf.calculated_at is not None:
        row["evaluation"]["observation_state"] = "insufficient_data"
        row["evaluation"]["missing"] = []
    row["evaluation"]["automatic_points"] = _decimal(block.get("automatic_points"), Decimal("8.5"))
    row["evaluation"]["covered_weight_pct"] = _decimal(
        block.get("covered_weight_pct"), Decimal("85")
    )
    # Overall score and grade remain exactly as they were on the existing API:
    # NULL until approved business/human decision logic computes them.
    _attach_saved_dimension_evidence(row, perf, coverage)
    # PR337_V4_EVIDENCE_READ_PROJECTION_20261114
    from .v4_evidence_projection import attach_v4_saved_evidence

    attach_v4_saved_evidence(row, perf, coverage)
    # PR337_SALESTAT_PERSISTED_VIEW_V5_20261114
    from .v5_reconciled_projection import correct_pending_v4_projection

    correct_pending_v4_projection(row, perf, coverage)
    # PR337_VERIFIED_SCORES_V6_LOCAL_20261114
    from .v6_sql_attested_view import apply_attested_current_view

    apply_attested_current_view(row, perf, coverage)
