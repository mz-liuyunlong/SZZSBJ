"""Verified initial new-product performance calculation.

Run manually with --dry-run first, then --apply only after CI and an isolated
production release. This does not start tracking, approve purchases or schedule
background work. All source reads use the existing read-only source dependency.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from app.db.session import get_session_factory

from .bulk_read import load_read_snapshot
from .models import (
    MarketScore,
    NewProductDailySnapshot,
    NewProductPerformanceCurrent,
    NewProductRegistry,
    RuleVersion,
)
from .read_source import get_new_product_read_session
from .scoring import evaluate
from .service import NewProductService, serialized

LOG = logging.getLogger(__name__)
LA = ZoneInfo("America/Los_Angeles")
BATCH = 80
REFUNDS_SQL = text("""
WITH wanted AS (
    SELECT account, store, item, start_date, end_date
    FROM jsonb_to_recordset(CAST(:wanted AS jsonb)) AS j(
        account text, store text, item text, start_date date, end_date date
    )
)
SELECT w.account, w.store, w.item, a.return_order_id, a.return_qty,
       COALESCE(NULLIF(a.manual_reason_code, ''),
                NULLIF(a.normalized_reason_code, ''),
                NULLIF(a.return_reason_code, '')) AS reason_code
FROM wanted w
JOIN after_sales_refund_items a
  ON a.source_account_ref=w.account
 AND a.store_id=w.store
 AND a.item_id=w.item
WHERE a.refund_completed IS TRUE
  AND a.purchase_time_at IS NOT NULL
  AND (a.purchase_time_at AT TIME ZONE 'America/Los_Angeles')::date
      BETWEEN w.start_date AND w.end_date
""")


def _number(value):
    return Decimal(str(value)) if value is not None else None


def summarize_daily(rows: list[dict]) -> dict:
    """Never equate missing sales rows with verified zero activity."""
    result = {
        "sales_units": None,
        "sales_orders": None,
        "sales_amount_usd": None,
        "profit_usd": None,
        "sample_units": None,
        "roi": None,
        "profit_margin_pct": None,
    }
    if not rows:
        return result

    if all(r.get("sales_qty") is not None for r in rows):
        result["sales_units"] = sum((_number(r["sales_qty"]) for r in rows), Decimal(0))
    if all(r.get("order_count") is not None for r in rows):
        orders = sum((_number(r["order_count"]) for r in rows), Decimal(0))
        if orders == orders.to_integral_value():
            result["sales_orders"] = int(orders)
    if all(
        r.get("sales_amount") is not None and r.get("sales_currency_code") == "USD"
        for r in rows
    ):
        result["sales_amount_usd"] = sum(
            (_number(r["sales_amount"]) for r in rows), Decimal(0)
        )

    if all(
        r.get("cost_status") == "complete"
        and r.get("gross_profit_amount") is not None
        and r.get("gross_profit_currency_code") == "USD"
        and r.get("purchase_cost_total_usd") is not None
        and r.get("first_leg_cost_total_usd") is not None
        for r in rows
    ):
        profit = sum((_number(r["gross_profit_amount"]) for r in rows), Decimal(0))
        cost = sum(
            (
                _number(r["purchase_cost_total_usd"])
                + _number(r["first_leg_cost_total_usd"])
                for r in rows
            ),
            Decimal(0),
        )
        result["profit_usd"] = profit
        if cost > 0:
            result["roi"] = profit / cost
        revenue = result["sales_amount_usd"]
        if revenue is not None and revenue > 0:
            result["profit_margin_pct"] = profit / revenue * 100
    return result


def summarize_ad(ads: dict | None, sales_usd: Decimal | None) -> dict:
    result = {
        "ad_spend_usd": None,
        "ad_clicks": None,
        "ad_sales_usd": None,
        "ad_spend_ratio_pct": None,
        "acos_pct": None,
    }
    if not ads or not ads.get("n"):
        return result
    if not ads.get("spend_missing") and ads.get("spend") is not None:
        result["ad_spend_usd"] = _number(ads["spend"])
    if not ads.get("clicks_missing") and ads.get("clicks") is not None:
        result["ad_clicks"] = int(ads["clicks"])
    if not ads.get("incomplete") and ads.get("revenue") is not None:
        result["ad_sales_usd"] = _number(ads["revenue"])
    spend = result["ad_spend_usd"]
    ad_sales = result["ad_sales_usd"]
    if spend is not None and sales_usd is not None and sales_usd > 0:
        result["ad_spend_ratio_pct"] = spend / sales_usd * 100
    if spend is not None and ad_sales is not None and ad_sales > 0:
        result["acos_pct"] = spend / ad_sales * 100
    return result


def _read_refunds(session: Session, keys: list[tuple[str, str, str]], first, through):
    windows = [
        {
            "account": a,
            "store": s,
            "item": i,
            "start_date": first[(a, s, i)]["day"].isoformat(),
            "end_date": min(first[(a, s, i)]["day"] + timedelta(days=13), through).isoformat(),
        }
        for a, s, i in keys
        if first.get((a, s, i), {}).get("day") is not None
        and first[(a, s, i)]["day"] <= through
    ]
    result = defaultdict(list)
    if not windows:
        return result
    for r in session.execute(
        REFUNDS_SQL, {"wanted": json.dumps(windows, separators=(",", ":"))}
    ).mappings():
        result[(r["account"], r["store"], r["item"])].append(dict(r))
    return result


def summarize_refunds(rows: list[dict], sold_units, sold_orders) -> dict:
    result = {
        "returned_units": None,
        "returned_orders": None,
        "return_rate_units_pct": None,
        "return_rate_orders_pct": None,
        "return_reasons_json": None,
    }
    if not rows or any(r.get("return_qty") is None for r in rows):
        return result
    units = sum((_number(r["return_qty"]) for r in rows), Decimal(0))
    orders = len({r["return_order_id"] for r in rows if r.get("return_order_id")})
    result["returned_units"] = units
    result["returned_orders"] = orders
    if sold_units is not None and sold_units > 0:
        result["return_rate_units_pct"] = units / sold_units * 100
    if sold_orders is not None and sold_orders > 0:
        result["return_rate_orders_pct"] = Decimal(orders) / sold_orders * 100
    reason_counts = defaultdict(int)
    for row in rows:
        reason_counts[row.get("reason_code") or "UNCLASSIFIED"] += 1
    result["return_reasons_json"] = {
        "source": "after_sales_refund_items",
        "counts_by_code": dict(sorted(reason_counts.items())),
        "scope": "original_purchase_within_first_14_wfs_days",
    }
    return result


def calculate(*, through: date, apply: bool = False) -> dict:
    """One bounded, all-or-nothing run; no side effects when apply=False."""
    if through > datetime.now(LA).date() - timedelta(days=1):
        raise ValueError("Only completed LA business dates may be calculated")
    with get_session_factory()() as writer:
        locked = writer.scalar(text("SELECT pg_try_advisory_xact_lock(337, 89)"))
        if not locked:
            raise RuntimeError("A new-product calculation is already running")
        registries = writer.scalars(
            select(NewProductRegistry)
            .where(NewProductRegistry.is_currently_tagged.is_(True))
            .order_by(
                NewProductRegistry.source_account_ref,
                NewProductRegistry.store_id,
                NewProductRegistry.item_id,
            )
        ).all()
        if not registries or len(registries) > 20000:
            raise RuntimeError("Unexpected enrollment count; refusing calculation")

        service = NewProductService(writer)
        config, rule_version = service._config()
        rule_row = service.write_repo.rule_version("performance")
        if not rule_row:
            rule_version = 0
        keys = [(r.source_account_ref, r.store_id, r.item_id) for r in registries]
        market_map = {
            (r.source_account_ref, r.store_id, r.item_id): r
            for r in writer.scalars(
                select(MarketScore).where(
                    tuple_(
                        MarketScore.source_account_ref,
                        MarketScore.store_id,
                        MarketScore.item_id,
                    ).in_(keys)
                )
            ).all()
        }
        current_map = {
            row.registry_id: row
            for row in writer.scalars(
                select(NewProductPerformanceCurrent).where(
                    NewProductPerformanceCurrent.registry_id.in_([r.id for r in registries])
                )
            ).all()
        }
        existing = set(
            writer.scalars(
                select(NewProductDailySnapshot.registry_id).where(
                    NewProductDailySnapshot.phase == "performance",
                    NewProductDailySnapshot.snapshot_date_la == through,
                )
            ).all()
        )
        counts = {"eligible": len(registries), "known_first_wfs": 0, "sales": 0,
                  "ads": 0, "refunds": 0, "graded": 0, "snapshots_new": 0,
                  "missing_first_wfs": 0, "mode": "apply" if apply else "dry_run"}
        now = datetime.now(UTC)
        with contextmanager(get_new_product_read_session)() as source:
            for offset in range(0, len(registries), BATCH):
                batch = registries[offset:offset + BATCH]
                batch_keys = [
                    (r.source_account_ref, r.store_id, r.item_id) for r in batch
                ]
                snapshot = load_read_snapshot(source, batch_keys, through)
                refunds = _read_refunds(source, batch_keys, snapshot.first, through)
                for registry in batch:
                    key = (
                        registry.source_account_ref, registry.store_id, registry.item_id
                    )
                    first_day = snapshot.first.get(key, {}).get("day")
                    facts = service._facts(
                        *key, market_score=market_map.get(key),
                        snapshot=snapshot, as_of_la=through
                    )
                    evaluation = evaluate(facts, config, rule_version)
                    daily = snapshot.daily.get(key, [])
                    sales = summarize_daily(daily)
                    ad = summarize_ad(
                        snapshot.ads.get(key), sales["sales_amount_usd"]
                    )
                    ret = summarize_refunds(
                        refunds.get(key, []),
                        sales["sales_units"],
                        sales["sales_orders"],
                    )
                    metrics = {**sales, **ad, **ret}
                    counts["known_first_wfs" if first_day else "missing_first_wfs"] += 1
                    counts["sales"] += int(bool(daily))
                    counts["ads"] += int(bool(snapshot.ads.get(key, {}).get("n")))
                    counts["refunds"] += int(bool(refunds.get(key)))
                    grade = (
                        evaluation["grade"]
                        if rule_version > 0 and not evaluation["missing"]
                        else None
                    )
                    counts["graded"] += int(bool(grade))
                    status = (
                        "missing_first_wfs" if first_day is None
                        else "available" if grade else "partial"
                    )
                    coverage = {
                        "source": "pr337_verified_14_day_observation",
                        "as_of_la": through.isoformat(),
                        "first_stock_known": first_day is not None,
                        "sales_day_rows": len(daily),
                        "ad_fact_rows": int(snapshot.ads.get(key, {}).get("n") or 0),
                        "completed_refund_rows": len(refunds.get(key, [])),
                        "rule_published": rule_version > 0,
                        "evaluation": serialized(evaluation),
                        "missing": evaluation["missing"],
                    }
                    if not apply:
                        continue
                    row = current_map.get(registry.id)
                    if row is None:
                        raise RuntimeError("Missing registry performance row")
                    row.metric_window_start_la = first_day
                    row.metric_window_end_la = (
                        min(first_day + timedelta(days=13), through)
                        if first_day is not None and first_day <= through else None
                    )
                    first_order = snapshot.orders.get(key, {}).get("first_order_date")
                    if first_order:
                        row.first_order_date_la = first_order
                    for field, value in metrics.items():
                        if value is not None:
                            setattr(row, field, value)
                    if grade:
                        row.score = _number(evaluation["total"])
                        row.grade = grade
                        row.rule_version_id = rule_row.id
                    row.data_status = status
                    row.process_status = evaluation["observation_state"]
                    row.data_coverage_json = coverage
                    row.calculated_at = now
                    row.updated_at = now
                    if registry.id not in existing:
                        writer.add(
                            NewProductDailySnapshot(
                                id=uuid4(),
                                registry_id=registry.id,
                                phase="performance",
                                snapshot_date_la=through,
                                metric_window_start_la=row.metric_window_start_la,
                                metric_window_end_la=row.metric_window_end_la,
                                score=_number(evaluation["total"]) if grade else None,
                                grade=grade,
                                data_status=status,
                                source_coverage_json=coverage,
                                metrics_json=serialized({
                                    "facts": facts,
                                    "evaluation": evaluation,
                                    "observed_metrics": metrics,
                                }),
                                rule_version_id=rule_row.id if grade else None,
                                **{
                                    field: value for field, value in metrics.items()
                                    if field in NewProductDailySnapshot.__table__.c
                                },
                            )
                        )
                        counts["snapshots_new"] += 1
        if apply:
            writer.commit()
        else:
            writer.rollback()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="New-product initial observed metrics")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--through-la", type=date.fromisoformat)
    args = parser.parse_args()
    through = args.through_la or datetime.now(LA).date() - timedelta(days=1)
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(calculate(through=through, apply=args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
