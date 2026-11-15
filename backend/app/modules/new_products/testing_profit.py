"""PR337: independent test-product profit, sourced read-only from Daily Sales.

This module does not change Daily Sales, financial data, or closed product data.
The mart already excludes validated samples from sales_qty/order_count/sales_amount;
refunds do not reduce those fields. Fulfillment totals may include samples and
commission_fee_amount is refund-adjusted, so neither is copied verbatim.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

Key = tuple[str, str, str]
ZERO = Decimal("0")
HUNDRED = Decimal("100")
LA = ZoneInfo("America/Los_Angeles")
FINAL_RESULTS = frozenset({"\u6253\u54c1\u6210\u529f", "\u6253\u54c1\u5931\u8d25"})


@dataclass(frozen=True)
class FinalDecision:
    result: str
    snapshot: dict[str, Any] | None
    decided_at: datetime | None = None
    legacy_facts: dict[str, Any] | None = None


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def scoped_keys(keys: Iterable[Key]) -> list[Key]:
    requested = list(dict.fromkeys(keys))
    if len(requested) > 200:
        raise ValueError("New-products batch must not exceed 200 identities")
    return requested


def keys_json(keys: Iterable[Key]) -> str:
    return json.dumps(
        [{"account": a, "store": s, "item": i} for a, s, i in keys],
        ensure_ascii=True,
        separators=(",", ":"),
    )


_FINALS_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,t.final_result,t.final_result_at,
       t.final_result_snapshot_json,d.decision AS legacy_decision,
       d.decided_at AS legacy_decided_at,d.evaluated_facts AS legacy_facts
FROM wanted w
LEFT JOIN biz_new_product_registry r
  ON r.source_account_ref=w.account AND r.store_id=w.store AND r.item_id=w.item
LEFT JOIN biz_new_product_tracking_current t ON t.registry_id=r.id
LEFT JOIN biz_new_product_tracking_decisions d
  ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
""")

# Never filter on first-paid-sale day: pre-sale and sample-day ad expense counts.
_DAILY_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,d.business_date_la AS day,
       d.sales_qty,d.order_count,d.sales_amount,d.sales_currency_code,
       d.sample_qty,d.cost_quantity,d.ad_spend_amount,d.sem_ad_spend_amount,
       d.ad_spend_currency_code,d.commission_rate,
       d.purchase_cost_total_usd,d.first_leg_cost_total_usd,
       d.wfs_fee_total_amount,d.wfs_fee_actual_total_amount,
       d.wfs_fee_expected_total_amount,d.wfs_low_price_surcharge_amount,
       d.storage_fee_total_amount,d.calculation_warnings_json
FROM wanted w JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
WHERE d.business_date_la <= :cutoff
ORDER BY w.account,w.store,w.item,d.business_date_la
""")

_ADS_SQL = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,
       COUNT(a.id) AS source_rows,
       COUNT(a.id) FILTER (
          WHERE a.ad_spend_amount IS NULL
             OR a.ad_spend_currency_code IS DISTINCT FROM 'USD'
       ) AS incomplete_spend_rows,
       SUM(a.ad_spend_amount) FILTER (
          WHERE a.ad_spend_currency_code='USD'
       ) AS sp_spend
FROM wanted w LEFT JOIN fact_walmart_ad_item_sp_daily a
 ON a.source_account_ref=w.account AND a.store_id=w.store AND a.item_id=w.item
 AND a.business_date_la <= :cutoff
GROUP BY w.account,w.store,w.item
""")


def load_final_decisions(session: Session, keys: Iterable[Key]) -> dict[Key, FinalDecision]:
    requested = scoped_keys(keys)
    if not requested:
        return {}
    results: dict[Key, FinalDecision] = {}
    for record in session.execute(_FINALS_SQL, {"wanted": keys_json(requested)}).mappings():
        row = dict(record)
        current, legacy = row.get("final_result"), row.get("legacy_decision")
        if current not in FINAL_RESULTS and legacy not in FINAL_RESULTS:
            continue
        selected = current if current in FINAL_RESULTS else legacy
        snapshot = row.get("final_result_snapshot_json")
        legacy_facts = row.get("legacy_facts")
        if not isinstance(snapshot, dict) and isinstance(legacy_facts, dict):
            snapshot = legacy_facts.get("__test_final_score_v2")
        decided_at = (
            row.get("final_result_at") if current in FINAL_RESULTS else row.get("legacy_decided_at")
        )
        results[(row["account"], row["store"], row["item"])] = FinalDecision(
            selected,
            snapshot if isinstance(snapshot, dict) else None,
            decided_at if isinstance(decided_at, datetime) else None,
            legacy_facts if isinstance(legacy_facts, dict) else None,
        )
    return results


def calculate_testing_profit(
    rows: Iterable[Mapping[str, Any]],
    *,
    sp_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate complete pre-closure historical normal-sale profit.

    Always exclude refunds, sample sales, sample fulfillment and sample materials.
    Preserve original costs for returned normal orders, and count all SP + SEM
    ad costs even before the first paid sale. Source SP spending comes from raw
    ad facts (not daily mart), avoiding identity gaps and double counting.
    """
    data = list(rows)
    missing: set[str] = set()
    revenue = paid_units = paid_orders = ZERO
    purchase = first_leg = wfs = storage = commission = sem = ZERO
    first_order: date | None = None

    for row in data:
        quantity = decimal_value(row.get("sales_qty"))
        orders = decimal_value(row.get("order_count"))
        sales = decimal_value(row.get("sales_amount"))
        sample = decimal_value(row.get("sample_qty"))
        cost_quantity = decimal_value(row.get("cost_quantity"))
        sem_amount = decimal_value(row.get("sem_ad_spend_amount"))
        if sem_amount is None or sem_amount < ZERO:
            missing.add("sem_ad_cost_missing")
        else:
            sem += sem_amount
        if any(v is None for v in (quantity, orders, sales, sample, cost_quantity)):
            missing.add("daily_sale_quantity_missing")
            continue
        if min(quantity, orders, sales, sample, cost_quantity) < ZERO:
            missing.add("negative_daily_values")
            continue
        if cost_quantity < quantity or cost_quantity < sample:
            missing.add("cost_quantity_inconsistent")
            continue
        if row.get("sales_currency_code") != "USD":
            missing.add("sales_currency_unverified")
            continue
        if "sample_exceeds_salestat_pending_review" in (row.get("calculation_warnings_json") or []):
            missing.add("sample_evidence_disputed")
            continue
        revenue += sales
        paid_units += quantity
        paid_orders += orders
        day = row.get("day")
        if orders > 0 and isinstance(day, date) and (first_order is None or day < first_order):
            first_order = day
        if quantity == 0:
            # This may be a sample-only day; SEM spend above still counts.
            continue
        if cost_quantity <= 0:
            missing.add("cost_quantity_zero")
            continue
        share = quantity / cost_quantity
        for field, label in (
            ("purchase_cost_total_usd", "purchase_cost_missing"),
            ("first_leg_cost_total_usd", "first_leg_cost_missing"),
            ("storage_fee_total_amount", "storage_cost_missing"),
        ):
            value = decimal_value(row.get(field))
            if value is None or value < ZERO:
                missing.add(label)
                continue
            if field == "purchase_cost_total_usd":
                purchase += value * share
            elif field == "first_leg_cost_total_usd":
                first_leg += value * share
            else:
                storage += value * share

        # The existing commission_fee_amount is refund-adjusted. Never reuse it.
        rate = decimal_value(row.get("commission_rate"))
        if rate is None or not ZERO <= rate <= Decimal("1"):
            missing.add("commission_rate_missing")
        else:
            commission += sales * rate

        actual = decimal_value(row.get("wfs_fee_actual_total_amount"))
        total = decimal_value(row.get("wfs_fee_total_amount"))
        expected = decimal_value(row.get("wfs_fee_expected_total_amount"))
        surcharge = decimal_value(row.get("wfs_low_price_surcharge_amount"))
        if sample > 0:
            # A combined actual charge cannot be attributed to paid vs sample
            # orders. Use the existing daily expected-unit-cost basis for paid
            # units only; if unavailable mark the profit incomplete.
            if expected is None or surcharge is None:
                missing.add("sample_wfs_split_unavailable")
            else:
                wfs += expected * share + surcharge
        elif actual is not None and surcharge is not None:
            wfs += actual + surcharge
        elif expected is not None and surcharge is not None:
            wfs += expected + surcharge
        elif total is not None:
            wfs += total
        else:
            missing.add("wfs_cost_missing")

    sp_rows = int((sp_data or {}).get("source_rows") or 0)
    bad_sp_rows = int((sp_data or {}).get("incomplete_spend_rows") or 0)
    sp_amount = decimal_value((sp_data or {}).get("sp_spend"))
    if sp_rows > 0 and (bad_sp_rows > 0 or sp_amount is None or sp_amount < ZERO):
        missing.add("sp_ad_cost_missing_or_currency_unverified")
    sp = sp_amount if sp_amount is not None and bad_sp_rows == 0 else ZERO
    # Daily Sales SP is only a fallback when *no* matching source SP records
    # exist, so it cannot be counted twice.
    if sp_rows == 0:
        for row in data:
            raw = decimal_value(row.get("ad_spend_amount"))
            if raw is None or raw < ZERO or row.get("ad_spend_currency_code") != "USD":
                missing.add("fallback_sp_ad_cost_unverified")
            else:
                sp += raw

    ad_spend = sp + sem
    if not data:
        missing.add("no_daily_sales_rows")
    if revenue <= ZERO or purchase + first_leg <= ZERO:
        missing.add("no_positive_sale_or_investment")
    if paid_units <= ZERO:
        missing.add("no_paid_sales")
    profit = revenue - (purchase + first_leg + wfs + storage + commission + ad_spend)
    invested = purchase + first_leg
    valid = not missing
    return {
        "status": "scored" if valid else "partial",
        "missing": sorted(missing),
        "profit_usd": str(profit) if valid else None,
        "roi": str(profit / invested) if valid else None,
        "gross_margin_pct": str(profit / revenue * HUNDRED) if valid else None,
        "sales_amount_usd": str(revenue),
        "sales_units": str(paid_units),
        "sales_orders": str(paid_orders),
        "sp_ad_spend_usd": str(sp)
        if "sp_ad_cost_missing_or_currency_unverified" not in missing
        and "fallback_sp_ad_cost_unverified" not in missing
        else None,
        "sem_ad_spend_usd": str(sem) if "sem_ad_cost_missing" not in missing else None,
        "ad_spend_usd": str(ad_spend)
        if not any(
            x in missing
            for x in (
                "sp_ad_cost_missing_or_currency_unverified",
                "sem_ad_cost_missing",
                "fallback_sp_ad_cost_unverified",
            )
        )
        else None,
        "first_order_date": first_order.isoformat() if first_order else None,
        "source": "mart_daily_sales_item_day+fact_walmart_ad_item_sp_daily",
        "policy": "returns_ignored_samples_excluded_sample_ads_included",
    }


def load_testing_profit_page(
    session: Session, keys: Iterable[Key], cutoff: date
) -> dict[Key, dict[str, Any]]:
    requested = scoped_keys(keys)
    if not requested:
        return {}
    wanted = keys_json(requested)
    grouped: dict[Key, list[dict[str, Any]]] = defaultdict(list)
    for record in session.execute(_DAILY_SQL, {"wanted": wanted, "cutoff": cutoff}).mappings():
        row = dict(record)
        grouped[(row["account"], row["store"], row["item"])].append(row)
    sp_map = {
        (r["account"], r["store"], r["item"]): dict(r)
        for r in session.execute(_ADS_SQL, {"wanted": wanted, "cutoff": cutoff}).mappings()
    }
    return {
        key: calculate_testing_profit(grouped.get(key, []), sp_data=sp_map.get(key))
        for key in requested
    }
