"""Verified SKU metrics from published business marts; no PMC or procurement dependencies."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.new_product_workflow.rules import compute_launch_result, compute_new_product_score

PERIODS = (30, 60, 90)


def la_today() -> date:
    return datetime.now(ZoneInfo("America/Los_Angeles")).date()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def read_sku_metrics(
    session: Session,
    *,
    account: str,
    sku: str,
    market_score: int | None,
    rule_version: int,
    rules: dict[str, Any],
    as_of: date | None = None,
) -> dict[str, Any]:
    """Last completed LA business day, with exclusive end-boundary and null-safe coverage.

    Profit mart is the sole source for sales/profit/ad spend; ad fact contributes clicks only.
    The account/store/item listing mapping avoids cross-store advertiser attribution.
    """
    end = as_of or la_today()
    periods: dict[str, dict[str, Any]] = {}
    for days in PERIODS:
        start = end - timedelta(days=days)
        params = {"account": account, "sku": sku, "start": start, "end": end}
        sales = session.execute(
            text(
                """
                SELECT count(*) AS observed_days,
                       sum(sales_qty) AS sales_qty,
                       sum(order_count) AS orders,
                       sum(sales_amount) AS sales_amount,
                       sum(ad_spend_amount) AS ad_spend,
                       sum(gross_profit_amount) AS profit,
                       sum(CASE WHEN cost_status = 'complete' THEN 1 ELSE 0 END)
                           AS complete_cost_days,
                       count(DISTINCT gross_profit_currency_code)
                           FILTER (WHERE gross_profit_currency_code IS NOT NULL) AS currencies
                FROM mart_order_profit_sku_day
                WHERE source_account_ref = :account AND local_sku = :sku
                  AND business_date_la >= :start AND business_date_la < :end
                """
            ),
            params,
        ).mappings().one()
        clicks = session.execute(
            text(
                """
                SELECT sum(ad.num_ads_clicks) AS clicks,
                       count(DISTINCT ad.business_date_la) AS ad_days
                FROM fact_walmart_ad_item_sp_daily AS ad
                WHERE ad.source_account_ref = :account
                  AND ad.business_date_la >= :start AND ad.business_date_la < :end
                  AND EXISTS (
                    SELECT 1 FROM dim_walmart_listings AS listing
                    WHERE listing.source_account_ref = ad.source_account_ref
                      AND listing.store_id = ad.store_id
                      AND listing.item_id = ad.item_id
                      AND listing.local_sku = :sku
                  )
                """
            ),
            params,
        ).mappings().one()
        profit = _number(sales["profit"])
        sales_amount = _number(sales["sales_amount"])
        ad_spend = _number(sales["ad_spend"])
        cost_days = int(sales["complete_cost_days"] or 0)
        observed = int(sales["observed_days"] or 0)
        margin = (profit / sales_amount * 100) if (
            cost_days == observed and observed > 0 and sales_amount is not None
            and sales_amount > 0 and profit is not None
            and int(sales["currencies"] or 0) == 1
        ) else None
        acos = (ad_spend / sales_amount * 100) if (
            ad_spend is not None and sales_amount is not None and sales_amount > 0
        ) else None
        # Missing days or incomplete cost valuation are never silently filled with zero.
        periods[str(days)] = {
            "days": days,
            "from": start.isoformat(),
            "to_exclusive": end.isoformat(),
            "sales": _number(sales["sales_qty"]),
            "orders": _number(sales["orders"]),
            "revenue": sales_amount,
            "ad_spend": ad_spend,
            "clicks": int(clicks["clicks"]) if clicks["clicks"] is not None else None,
            "ad_days": int(clicks["ad_days"] or 0),
            "profit": profit if cost_days == observed and observed > 0 else None,
            "margin": margin,
            "acos": acos,
            "observed_days": observed,
            "complete_cost_days": cost_days,
            "complete": observed == days and cost_days == days and margin is not None
            and ad_spend is not None and clicks["clicks"] is not None,
        }

    inv = session.execute(
        text(
            """
            SELECT sum(available_quantity) AS available,
                   sum(wfs_available_quantity) AS wfs_available,
                   count(*) AS listing_count, max(calculated_at) AS refreshed_at
            FROM mart_listing_management_current
            WHERE source_account_ref = :account AND local_sku = :sku
            """
        ),
        {"account": account, "sku": sku},
    ).mappings().one()
    inventory = {
        "available": _number(inv["available"]),
        "wfs_available": _number(inv["wfs_available"]),
        "listing_count": int(inv["listing_count"] or 0),
        "refreshed_at": inv["refreshed_at"].isoformat() if inv["refreshed_at"] else None,
        "note": "Available and WFS quantities reported separately; do not add them.",
    }
    # The listing publication date is not a proven warehouse-arrival/sellable date.
    # Therefore no automatic final success/failure without verified operational dates.
    result = {
        "account": account,
        "sku": sku,
        "business_timezone": "America/Los_Angeles",
        "as_of_exclusive": end.isoformat(),
        "source_tables": [
            "mart_order_profit_sku_day",
            "fact_walmart_ad_item_sp_daily",
            "dim_walmart_listings",
            "mart_listing_management_current",
        ],
        "periods": periods,
        "inventory": inventory,
        "rule_version": rule_version,
    }
    result["score"] = compute_new_product_score(
        market_score=market_score, metrics=periods["30"], rules=rules,
        rule_version=rule_version,
    )
    result["launch"] = compute_launch_result(
        metrics=periods[str(rules.get("success_days", 60))], rules=rules,
        start_date=None, as_of=end,
    )
    return result
