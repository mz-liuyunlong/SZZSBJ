"""Read-only account/SKU data integrity checks for #278.

This reports evidence from real DB rows when an authorized user calls it.
It never guesses missing business days are zero, imputes a currency, or
claims that a reconciled derived mart proves the upstream source was complete.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _money(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _count(value: Any) -> int:
    return int(value or 0)


def reconcile_new_product_source(
    session: Session,
    *,
    account: str,
    sku: str,
    start: date,
    end: date,
    include_financial_values: bool,
) -> dict[str, Any]:
    days = (end - start).days
    if not account or not sku or not 1 <= days <= 90:
        raise ValueError("a scoped SKU and a 1-90-day LA reporting window are required")
    params = {"account": account, "sku": sku, "start": start, "end": end}
    listing = (
        session.execute(
            text(
                """
                SELECT count(*) AS listing_rows,
                       count(DISTINCT store_id) AS stores,
                       count(DISTINCT (store_id, item_id)) AS store_item_pairs,
                       count(DISTINCT item_id) AS item_ids,
                       min((listing_start_at_utc AT TIME ZONE
                           'America/Los_Angeles')::date) AS first_listing_date,
                       count(*) FILTER (WHERE listing_start_at_utc IS NULL)
                           AS missing_listing_start_rows
                FROM dim_walmart_listings
                WHERE source_account_ref = :account AND local_sku = :sku
                """
            ),
            params,
        )
        .mappings()
        .one()
    )
    sku_day = (
        session.execute(
            text(
                """
                SELECT count(DISTINCT business_date_la) AS days,
                       count(*) FILTER (WHERE sales_qty = 0) AS recorded_zero_days,
                       sum(sales_qty) AS qty, sum(order_count) AS orders,
                       sum(sales_amount) AS sales_amount,
                       sum(gross_profit_amount) AS gross_profit,
                       count(*) FILTER (WHERE cost_status <> 'complete') AS missing_cost_rows,
                       count(*) FILTER (
                           WHERE sales_currency_code IS NULL OR gross_profit_currency_code IS NULL
                       ) AS missing_currency_rows,
                       count(DISTINCT sales_currency_code) AS revenue_currency_count,
                       count(DISTINCT gross_profit_currency_code) AS profit_currency_count,
                       min(sales_currency_code) AS revenue_currency,
                       min(gross_profit_currency_code) AS profit_currency
                FROM mart_order_profit_sku_day
                WHERE source_account_ref = :account AND local_sku = :sku
                  AND business_date_la >= :start AND business_date_la < :end
                """
            ),
            params,
        )
        .mappings()
        .one()
    )
    item_day = (
        session.execute(
            text(
                """
                SELECT count(*) AS rows, count(DISTINCT business_date_la) AS days,
                       count(DISTINCT (store_id, item_id)) AS store_item_pairs,
                       sum(sales_qty) AS qty,
                       sum(order_count) AS orders,
                       sum(sales_amount) AS sales_amount,
                       count(DISTINCT sales_currency_code) AS currency_count,
                       count(*) FILTER (WHERE sales_currency_code IS NULL)
                           AS missing_currency_rows
                FROM mart_daily_sales_item_day
                WHERE source_account_ref = :account AND local_sku = :sku
                  AND business_date_la >= :start AND business_date_la < :end
                """
            ),
            params,
        )
        .mappings()
        .one()
    )
    ads = (
        session.execute(
            text(
                """
                WITH sku_listing AS (
                    SELECT DISTINCT store_id, item_id FROM dim_walmart_listings
                    WHERE source_account_ref = :account AND local_sku = :sku
                )
                SELECT count(*) AS candidate_rows,
                       count(*) FILTER (WHERE listing.store_id IS NOT NULL) AS matched_rows,
                       count(*) FILTER (WHERE listing.store_id IS NULL) AS unmatched_rows,
                       count(DISTINCT ad.business_date_la) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS observed_ad_days,
                       count(*) FILTER (
                           WHERE listing.store_id IS NOT NULL
                             AND ad.ad_spend_amount IS NOT NULL
                             AND ad.ad_spend_currency_code IS NULL
                       ) AS spend_without_currency,
                       count(*) FILTER (
                           WHERE listing.store_id IS NOT NULL
                             AND ad.attributed_sales_amount IS NOT NULL
                             AND ad.attributed_sales_currency_code IS NULL
                       ) AS attributed_without_currency,
                       count(DISTINCT ad.ad_spend_currency_code) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS spend_currency_count,
                       count(DISTINCT ad.attributed_sales_currency_code) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS attributed_currency_count,
                       min(ad.ad_spend_currency_code) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS spend_currency,
                       min(ad.attributed_sales_currency_code) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS attributed_currency,
                       sum(ad.ad_spend_amount) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS ad_spend,
                       sum(ad.attributed_sales_amount) FILTER (
                           WHERE listing.store_id IS NOT NULL
                       ) AS attributed_sales
                FROM fact_walmart_ad_item_sp_daily AS ad
                LEFT JOIN sku_listing AS listing
                  ON listing.store_id = ad.store_id
                 AND listing.item_id = ad.item_id
                WHERE ad.source_account_ref = :account
                  AND ad.business_date_la >= :start
                  AND ad.business_date_la < :end
                  AND ad.item_id IN (SELECT item_id FROM sku_listing)
                """
            ),
            params,
        )
        .mappings()
        .one()
    )
    issues: list[str] = []
    if _count(listing["listing_rows"]) == 0:
        issues.append("no_account_sku_item_mapping")
    if _count(listing["missing_listing_start_rows"]) > 0:
        issues.append("listing_start_date_missing")
    if _count(sku_day["days"]) != days:
        issues.append("sales_mart_business_days_unverified")
    if _count(sku_day["missing_cost_rows"]) > 0:
        issues.append("financial_cost_coverage_incomplete")
    if _count(sku_day["missing_currency_rows"]) > 0:
        issues.append("financial_currency_missing")
    if (
        _count(sku_day["revenue_currency_count"]) != 1
        or _count(sku_day["profit_currency_count"]) != 1
        or sku_day["revenue_currency"] != sku_day["profit_currency"]
    ):
        issues.append("profit_revenue_currency_conflict")
    if _count(item_day["rows"]) == 0:
        issues.append("item_sales_source_missing")
    if _count(ads["unmatched_rows"]) > 0:
        issues.append("candidate_ads_without_exact_store_item_mapping")
    if _count(ads["matched_rows"]) == 0:
        issues.append("ads_matching_unverified")
    if _count(ads["observed_ad_days"]) != days:
        issues.append("advertiser_day_coverage_unverified")
    if _count(ads["spend_without_currency"]) > 0:
        issues.append("ad_spend_currency_missing")
    if _count(ads["attributed_without_currency"]) > 0:
        issues.append("attributed_sales_currency_missing")
    same_ad_currency = (
        _count(ads["spend_currency_count"]) == 1
        and _count(ads["attributed_currency_count"]) == 1
        and ads["spend_currency"] == ads["attributed_currency"]
        and _count(ads["spend_without_currency"]) == 0
        and _count(ads["attributed_without_currency"]) == 0
    )
    if not same_ad_currency:
        issues.append("attribution_currency_not_reconciled")
    if (
        _money(sku_day["qty"]) is not None
        and _money(item_day["qty"]) is not None
        and _money(sku_day["qty"]) != _money(item_day["qty"])
    ):
        issues.append("sales_qty_sku_vs_item_mart_mismatch")
    finance: dict[str, Any] = {"visibility": "restricted"}
    if include_financial_values:
        finance = {
            "visibility": "authorized",
            "sku_sales_amount": None,
            "item_sales_amount": None,
            "sales_difference": None,
            "gross_profit_amount": None,
            "ad_spend_amount": None,
            "attributed_sales_amount": None,
            "roas": None,
        }
        finance_consistent = (
            _count(sku_day["missing_currency_rows"]) == 0
            and _count(sku_day["revenue_currency_count"]) == 1
            and _count(item_day["currency_count"]) == 1
            and _count(item_day["missing_currency_rows"]) == 0
        )
        if finance_consistent:
            master = _money(sku_day["sales_amount"])
            detail = _money(item_day["sales_amount"])
            if master is not None and detail is not None:
                finance["sku_sales_amount"] = float(master)
                finance["item_sales_amount"] = float(detail)
                finance["sales_difference"] = float(master - detail)
                if abs(master - detail) > Decimal("0.0001"):
                    issues.append("sales_amount_sku_vs_item_mart_mismatch")
        if (
            _count(sku_day["missing_cost_rows"]) == 0
            and _count(sku_day["missing_currency_rows"]) == 0
            and sku_day["revenue_currency"] == sku_day["profit_currency"]
        ):
            profit = _money(sku_day["gross_profit"])
            finance["gross_profit_amount"] = float(profit) if profit is not None else None
        if same_ad_currency:
            spend = _money(ads["ad_spend"])
            sales = _money(ads["attributed_sales"])
            finance["ad_spend_amount"] = float(spend) if spend is not None else None
            finance["attributed_sales_amount"] = float(sales) if sales is not None else None
            if spend is not None and spend > 0 and sales is not None:
                finance["roas"] = float(sales / spend)
    return {
        "account": account,
        "sku": sku,
        "window": {"from": start.isoformat(), "to_exclusive": end.isoformat(), "days": days},
        "mapping": {
            "listing_rows": _count(listing["listing_rows"]),
            "stores": _count(listing["stores"]),
            "item_ids": _count(listing["item_ids"]),
            "store_item_pairs": _count(listing["store_item_pairs"]),
            "first_listing_date": (
                listing["first_listing_date"].isoformat()
                if listing["first_listing_date"] is not None
                else None
            ),
        },
        "sales": {
            "mart_days": _count(sku_day["days"]),
            "recorded_zero_days": _count(sku_day["recorded_zero_days"]),
            "item_mart_days": _count(item_day["days"]),
            "cost_missing_rows": _count(sku_day["missing_cost_rows"]),
            "currency": sku_day["revenue_currency"],
        },
        "ads": {
            "candidate_rows": _count(ads["candidate_rows"]),
            "matched_rows": _count(ads["matched_rows"]),
            "unmatched_rows": _count(ads["unmatched_rows"]),
            "observed_days": _count(ads["observed_ad_days"]),
            "spend_currency": ads["spend_currency"],
            "attributed_currency": ads["attributed_currency"],
        },
        "finance": finance,
        "zero_sales_days_verification": "source_publication_ledger_not_proven",
        "status": "blocked" if issues else "derived_tables_consistent_not_source_certified",
        "issues": sorted(set(issues)),
        "source_tables": [
            "dim_walmart_listings",
            "mart_order_profit_sku_day",
            "mart_daily_sales_item_day",
            "fact_walmart_ad_item_sp_daily",
        ],
        "read_only": True,
    }
