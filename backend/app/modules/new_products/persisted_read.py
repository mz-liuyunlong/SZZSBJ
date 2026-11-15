"""Read-only PR337 persisted business snapshots for scoped product identities.

The operational read session may point at the production read-only tunnel while
manual market scores remain in the separate local decision DB. This module does
not write, recalculate, or publish any scores.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .models import NewProductPerformanceCurrent, NewProductRegistry

Key = tuple[str, str, str]
Saved = tuple[NewProductRegistry, NewProductPerformanceCurrent | None]


def load_persisted(session: Session, keys: Iterable[Key]) -> dict[Key, Saved]:
    requested = list(dict.fromkeys(keys))
    if not requested:
        return {}
    if len(requested) > 200:
        raise ValueError("Persisted new-product page cannot exceed 200 identities")
    # Scope is always derived from the already authorized and tagged Listing page.
    statement = (
        select(NewProductRegistry, NewProductPerformanceCurrent)
        .outerjoin(
            NewProductPerformanceCurrent,
            NewProductPerformanceCurrent.registry_id == NewProductRegistry.id,
        )
        .where(
            tuple_(
                NewProductRegistry.source_account_ref,
                NewProductRegistry.store_id,
                NewProductRegistry.item_id,
            ).in_(requested)
        )
    )
    return {
        (registry.source_account_ref, registry.store_id, registry.item_id):
            (registry, performance)
        for registry, performance in session.execute(statement).all()
    }


def _value(value):
    return str(value) if value is not None else None


def _day(value):
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)[:10]


def snapshot_row(listing, first_order_date, saved: Saved | None, market, today: date):
    """Convert a persisted snapshot into the already deployed listing DTO.

    Never turn missing evidence into a zero, a final score, or a grade.
    """
    record = listing.model_dump(mode="json")
    first_day = listing.first_wfs_available_date_la
    registry, performance = saved if saved is not None else (None, None)
    coverage = performance.data_coverage_json if performance is not None else None
    coverage = coverage if isinstance(coverage, dict) else {}
    category = coverage.get("listing_category")
    category = category if isinstance(category, dict) else {}
    if category.get("leaf") and not record.get("category"):
        record["category"] = category["leaf"]
    elif registry is not None and not record.get("category"):
        record["category"] = registry.category_l2 or registry.category_l1
    if category.get("full_path"):
        record["category_path"] = category["full_path"]
    if registry is not None:
        record["category_l1"] = registry.category_l1
        record["category_l2"] = registry.category_l2
    if performance is not None and performance.first_wfs_available_date_la is not None:
        first_day = performance.first_wfs_available_date_la
    if isinstance(first_day, str):
        first_day = date.fromisoformat(first_day[:10])
    elapsed = (today - first_day).days + 1 if first_day and first_day <= today else None
    first_order = (
        performance.first_order_date_la
        if performance is not None and performance.first_order_date_la is not None
        else first_order_date
    )
    facts = {
        "first_wfs_available_date_la": _day(first_day),
        "first_order_date": _day(first_order),
        "elapsed_days": elapsed,
        "data_status": "not_calculated",
    }
    dims = {key: None for key in ("market", "speed", "ad", "profit", "trust")}
    market_score = market.score if market is not None else None
    facts["market_score"] = _value(market_score)
    if market_score is not None:
        dims["market"] = _value(market_score)
    auto = coverage.get("auto_dimension_scores")
    auto = auto if isinstance(auto, dict) else None
    rule_version = 0
    observation_state = "not_calculated"
    grade = None
    total = None
    if performance is not None:
        source_fields = {
            "roi": "roi",
            "gross_margin_pct": "profit_margin_pct",
            "ad_spend_usd": "ad_spend_usd",
            "ad_clicks": "ad_clicks",
            "ad_revenue_usd": "ad_sales_usd",
            "sales_units": "sales_units",
            "sales_orders": "sales_orders",
            "sales_amount_usd": "sales_amount_usd",
            "profit_usd": "profit_usd",
            "returned_units": "returned_units",
            "returned_orders": "returned_orders",
            "return_rate_units_pct": "return_rate_units_pct",
            "return_rate_orders_pct": "return_rate_orders_pct",
            "acos_pct": "acos_pct",
        }
        for response_field, model_field in source_fields.items():
            facts[response_field] = _value(getattr(performance, model_field))
        facts["metric_window_start_la"] = _day(performance.metric_window_start_la)
        facts["metric_window_end_la"] = _day(performance.metric_window_end_la)
        facts["data_cutoff_la"] = coverage.get("cutoff_la")
        facts["data_status"] = performance.data_status or (
            "available" if auto is not None else "not_calculated"
        )
        if auto is not None:
            observation_state = "calculated"
            dimensions = auto.get("dimensions") or {}
            if isinstance(dimensions, dict):
                for key in ("speed", "ad", "profit", "trust"):
                    value = dimensions.get(key)
                    dims[key] = str(value) if value is not None else None
            version = auto.get("rule_version")
            if isinstance(version, int) and version >= 0:
                rule_version = version
            facts["automatic_weighted_points"] = auto.get("automatic_weighted_points")
            facts["automatic_covered_weight_pct"] = auto.get("covered_weight_pct")
            facts["auto_score_source"] = auto.get("source")
        # Only persisted authoritative final values can ever become a final grade.
        grade = performance.grade
        total = _value(performance.score)
    missing = [key for key in ("market", "speed", "ad", "profit", "trust") if dims[key] is None]
    return {
        "listing": record,
        "facts": facts,
        "evaluation": {
            "rule_version": rule_version,
            "total": total,
            "grade": grade,
            "dimensions": dims,
            "missing": ["尚未执行后台评分"] if observation_state == "not_calculated" else missing,
            "ad_excluded": bool(auto and auto.get("ad_sample_insufficient")),
            "observation_state": observation_state,
        },
        "market_reason": market.reason if market is not None else None,
        "market_version": market.version if market is not None else 0,
        "purchase_status": None,
        "purchase_id": None,
        "tracking_decision": None,
        "tracking_reason": None,
        "system_recommendation": {
            "value": "待计算" if observation_state == "not_calculated" else "暂无法判定",
            "reasons": ["尚未执行后台计算"] if observation_state == "not_calculated"
                       else ["尚无完整系统建议依据"],
        },
        "suggested_qty": None,
    }
