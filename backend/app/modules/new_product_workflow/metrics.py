"""Verified SKU metrics from published business marts; no PMC or procurement dependencies."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.new_product_workflow.rules import compute_launch_result, compute_new_product_score
from app.modules.new_product_workflow.scoring_contract import formal_policy_gate

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
    start_date: date | None = None,
    score_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Last completed LA business day, with exclusive end-boundary and null-safe coverage.

    Daily Sales' SKU mart is authoritative for sales, existing net profit,
    SP spend and SEM spend; the ad fact contributes SP attribution and clicks
    for ACOS. Never deduct SP or SEM again from the published profit.
    The account/store/item listing mapping avoids cross-store advertiser attribution.
    """
    end = as_of or la_today()

    def read_window(start: date, window_end: date, days: int) -> dict[str, Any]:
        params = {"account": account, "sku": sku, "start": start, "end": window_end}
        sales = (
            session.execute(
                text(
                    """
                SELECT count(DISTINCT business_date_la) AS observed_days,
                       sum(sales_qty) AS sales_qty,
                       sum(order_count) AS orders,
                       sum(sales_amount) AS sales_amount,
                       sum(ad_spend_amount) AS sp_ad_spend,
                       sum(sem_ad_spend_amount) AS sem_ad_spend,
                       count(*) FILTER (WHERE ad_spend_amount IS NULL)
                           AS missing_sp_mart_rows,
                       count(*) FILTER (WHERE sem_ad_spend_amount IS NULL)
                           AS missing_sem_mart_rows,
                       sum(gross_profit_amount) AS profit,
                       sum(purchase_cost_total_usd) AS purchase_cost_total,
                       sum(first_leg_cost_total_usd) AS first_leg_cost_total,
                       count(*) FILTER (
                           WHERE purchase_cost_total_usd IS NULL
                              OR first_leg_cost_total_usd IS NULL
                       ) AS missing_investment_cost_rows,
                       count(DISTINCT business_date_la)
                           FILTER (WHERE cost_status = 'complete') AS complete_cost_days,
                       count(DISTINCT gross_profit_currency_code)
                           FILTER (WHERE gross_profit_currency_code IS NOT NULL) AS currencies,
                       count(DISTINCT sales_currency_code)
                           FILTER (WHERE sales_currency_code IS NOT NULL) AS sales_currencies,
                       min(sales_currency_code) AS sales_currency,
                       min(gross_profit_currency_code) AS profit_currency,
                       count(*) FILTER (
                           WHERE sales_currency_code IS NULL
                              OR gross_profit_currency_code IS NULL
                       ) AS missing_currency_rows
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
        clicks = (
            session.execute(
                text(
                    """
                SELECT sum(ad.num_ads_clicks) AS clicks,
                       sum(ad.ad_spend_amount) AS attributed_spend,
                       sum(ad.attributed_sales_amount) AS attributed_sales,
                       sum(ad.attributed_orders) AS attributed_orders,
                       sum(ad.num_ads_shown) AS impressions,
                       count(DISTINCT ad.ad_spend_currency_code)
                         FILTER (WHERE ad.ad_spend_currency_code IS NOT NULL)
                           AS spend_currencies,
                       count(DISTINCT ad.attributed_sales_currency_code)
                         FILTER (WHERE ad.attributed_sales_currency_code IS NOT NULL)
                           AS attributed_currencies,
                       min(ad.ad_spend_currency_code) AS spend_currency,
                       min(ad.attributed_sales_currency_code) AS attributed_currency,
                       count(*) FILTER (WHERE ad.ad_spend_currency_code IS NULL)
                           AS missing_spend_currency_rows,
                       count(*) FILTER (
                           WHERE ad.ad_spend_currency_code IS NULL
                              OR ad.attributed_sales_currency_code IS NULL
                       ) AS missing_ad_currency_rows,
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
            )
            .mappings()
            .one()
        )
        profit = _number(sales["profit"])
        sales_amount = _number(sales["sales_amount"])
        sp_ad_spend = _number(sales["sp_ad_spend"])
        sem_ad_spend = _number(sales["sem_ad_spend"])
        cost_days = int(sales["complete_cost_days"] or 0)
        observed = int(sales["observed_days"] or 0)
        consistent_currency = (
            int(sales["currencies"] or 0) == 1
            and int(sales["sales_currencies"] or 0) == 1
            and sales["sales_currency"] == sales["profit_currency"]
            and int(sales["missing_currency_rows"] or 0) == 0
        )
        margin = (
            (profit / sales_amount * 100)
            if (
                cost_days == observed
                and observed > 0
                and sales_amount is not None
                and sales_amount > 0
                and profit is not None
                and consistent_currency
            )
            else None
        )
        attributed_spend = _number(clicks["attributed_spend"])
        attributed_sales = _number(clicks["attributed_sales"])
        spend_currency_verified = (
            int(clicks["spend_currencies"] or 0) == 1
            and int(clicks["missing_spend_currency_rows"] or 0) == 0
            and clicks["spend_currency"] == sales["sales_currency"]
            and consistent_currency
        )
        # SEM costs are posted as USD by the existing Daily Sales MART builder.
        # The SKU profit MART does not carry a separate SEM currency column.
        # A positive SEM amount can only be combined with USD sales/profit.
        sem_currency_verified = (
            sem_ad_spend is not None
            and int(sales["missing_sem_mart_rows"] or 0) == 0
            and consistent_currency
            and (sem_ad_spend == 0 or sales["sales_currency"] == "USD")
        )
        sp_mart_verified = (
            sp_ad_spend is not None
            and int(sales["missing_sp_mart_rows"] or 0) == 0
            and spend_currency_verified
        )
        total_spend_verified = sp_mart_verified and sem_currency_verified
        total_ad_spend = (
            sp_ad_spend + sem_ad_spend
            if total_spend_verified and sp_ad_spend is not None and sem_ad_spend is not None
            else None
        )
        ads_same_currency = (
            int(clicks["spend_currencies"] or 0) == 1
            and int(clicks["attributed_currencies"] or 0) == 1
            and clicks["spend_currency"] == clicks["attributed_currency"]
            and int(clicks["missing_ad_currency_rows"] or 0) == 0
        )
        acos = (
            (attributed_spend / attributed_sales * 100)
            if (
                ads_same_currency
                and attributed_spend is not None
                and attributed_sales is not None
                and attributed_sales > 0
            )
            else None
        )
        ad_spend_ratio = (
            total_ad_spend / sales_amount * 100
            if total_ad_spend is not None and sales_amount is not None and sales_amount > 0
            else None
        )
        # Operating ROI reuses Daily Sales; formal grading ROI stays blocked.
        invested = (_number(sales["purchase_cost_total"]) or 0) + (
            _number(sales["first_leg_cost_total"]) or 0
        )
        roi_ready = (
            consistent_currency
            and cost_days == observed
            and observed == days
            and int(sales["missing_investment_cost_rows"] or 0) == 0
            and profit is not None
            and invested > 0
        )
        operating_roi = profit / invested if roi_ready else None
        roas = (
            attributed_sales / attributed_spend
            if ads_same_currency
            and attributed_sales is not None
            and attributed_spend is not None
            and attributed_spend > 0
            else None
        )
        clicks_count = _number(clicks["clicks"])
        ad_orders = _number(clicks["attributed_orders"])
        impressions = _number(clicks["impressions"])
        cpc = (
            attributed_spend / clicks_count
            if spend_currency_verified and attributed_spend is not None and clicks_count
            else None
        )
        cvr = ad_orders / clicks_count * 100 if ad_orders is not None and clicks_count else None
        ctr = clicks_count / impressions * 100 if clicks_count is not None and impressions else None
        # Never infer that an absent MART day means a genuine zero-sales day.
        # A source publication/completeness ledger is required for that distinction.
        issues: list[str] = []
        if observed != days:
            issues.append("missing_business_day_coverage")
        if cost_days != observed or observed == 0:
            issues.append("incomplete_cost_coverage")
        if not consistent_currency:
            issues.append("financial_currency_unverified")
        if margin is None:
            issues.append("margin_unavailable")
        if sp_ad_spend is None or sem_ad_spend is None:
            issues.append("ad_spend_unavailable")
        if not sp_mart_verified:
            issues.append("ad_spend_currency_unverified")
        if not sem_currency_verified:
            issues.append("sem_ad_spend_currency_unverified")
        if clicks["clicks"] is None:
            issues.append("ad_clicks_unavailable")
        # The ad fact might omit valid zero-spend days; without a publication
        # ledger those days cannot be declared complete or invented as zeros.
        if int(clicks["ad_days"] or 0) != days:
            issues.append("ad_coverage_unverified")
        if acos is None:
            issues.append("attributed_acos_unavailable")
        return {
            "days": days,
            "from": start.isoformat(),
            "to_exclusive": window_end.isoformat(),
            "sales": _number(sales["sales_qty"]),
            "orders": _number(sales["orders"]),
            "revenue": sales_amount if consistent_currency else None,
            "sp_ad_spend": sp_ad_spend if sp_mart_verified else None,
            "sem_ad_spend": sem_ad_spend if sem_currency_verified else None,
            "ad_spend": total_ad_spend,
            "clicks": int(clicks["clicks"]) if clicks["clicks"] is not None else None,
            "attributed_orders": ad_orders,
            "impressions": impressions,
            "cpc": cpc,
            "cvr": cvr,
            "ctr": ctr,
            "roas": roas,
            "roi": operating_roi,
            "roi_status": (
                "daily_sales_operating_roi"
                if roi_ready
                else "daily_sales_cost_or_coverage_unverified"
            ),
            "ad_days": int(clicks["ad_days"] or 0),
            "profit": (
                profit if cost_days == observed and observed > 0 and consistent_currency else None
            ),
            "margin": margin,
            "acos": acos,
            "ad_spend_ratio": ad_spend_ratio,
            "currency_code": sales["sales_currency"] if consistent_currency else None,
            "attributed_sales": attributed_sales if ads_same_currency else None,
            "observed_days": observed,
            "missing_days": max(days - observed, 0),
            "complete_cost_days": cost_days,
            "data_issues": issues,
            "complete": not issues,
        }

    periods: dict[str, dict[str, Any]] = {}
    for days in PERIODS:
        periods[str(days)] = read_window(end - timedelta(days=days), end, days)

    # Sales milestones are observations, not an approved score band.
    milestones: dict[str, Any] = {
        "first_order_date": None,
        "days_to_first_order": None,
        "sales_7d": None,
        "sales_10d": None,
        "sales_20d": None,
        "coverage_20d": None,
        "status": "awaiting_verified_sellable_date",
    }
    if start_date is not None:
        pace = (
            session.execute(
                text(
                    """
                    SELECT min(business_date_la) FILTER (WHERE sales_qty > 0)
                        AS first_order_date,
                        sum(sales_qty) FILTER (
                            WHERE business_date_la < :start + 7
                        ) AS sales_7d,
                        sum(sales_qty) FILTER (
                            WHERE business_date_la < :start + 10
                        ) AS sales_10d,
                        sum(sales_qty) FILTER (
                            WHERE business_date_la < :start + 20
                        ) AS sales_20d,
                        count(DISTINCT business_date_la) FILTER (
                            WHERE business_date_la < :start + 7
                        ) AS coverage_7d,
                        count(DISTINCT business_date_la) FILTER (
                            WHERE business_date_la < :start + 10
                        ) AS coverage_10d,
                        count(DISTINCT business_date_la) FILTER (
                            WHERE business_date_la < :start + 20
                        ) AS coverage_20d
                    FROM mart_order_profit_sku_day
                    WHERE source_account_ref = :account AND local_sku = :sku
                      AND business_date_la >= :start
                      AND business_date_la < :end
                    """
                ),
                {"account": account, "sku": sku, "start": start_date, "end": end},
            )
            .mappings()
            .one()
        )
        milestones["coverage_20d"] = int(pace["coverage_20d"] or 0)
        if (end - start_date).days < 20 or int(pace["coverage_20d"] or 0) != 20:
            milestones["status"] = "insufficient_business_day_coverage"
        else:
            milestones["status"] = "observed_not_formally_scored"
            first = pace["first_order_date"]
            milestones["first_order_date"] = first.isoformat() if first else None
            milestones["days_to_first_order"] = (first - start_date).days if first else None
            for window in (7, 10, 20):
                if int(pace[f"coverage_{window}d"] or 0) == window:
                    milestones[f"sales_{window}d"] = _number(pace[f"sales_{window}d"])

    inv = (
        session.execute(
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
        )
        .mappings()
        .one()
    )
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
        "verified_start_date": start_date.isoformat() if start_date else None,
        "order_milestones": milestones,
        "metric_definitions": {
            "acos": "attributed_spend / attributed_sales * 100; null if currency unknown",
            "ad_spend_ratio": (
                "(SKU MART SP ad_spend_amount + SEM sem_ad_spend_amount) / "
                "SKU MART sales_amount * 100, after component currency checks; not ACOS"
            ),
            "roas": "advertising attributed sales / advertising spend; not profit ROI",
            "roi": (
                "Daily Sales operating ROI = gross_profit / "
                "(purchase_cost_total_usd + first_leg_cost_total_usd); "
                "ratio not percent, not formal new-product grading ROI"
            ),
        },
        "source_tables": [
            "mart_order_profit_sku_day",
            "fact_walmart_ad_item_sp_daily",
            "dim_walmart_listings",
            "mart_listing_management_current",
        ],
        "periods": periods,
        "inventory": inventory,
        "rule_version": rule_version,
        "formal_policy": formal_policy_gate(rules),
    }
    result["score"] = compute_new_product_score(
        market_score=market_score,
        metrics=periods["30"],
        rules=rules,
        rule_version=rule_version,
        overrides=score_overrides,
    )
    launch_days = int(rules.get("success_days", 60))
    launch_window: dict[str, Any] = {}
    if start_date is not None:
        launch_end = start_date + timedelta(days=launch_days)
        if launch_end <= end:
            # The first complete launch window is immutable; never substitute
            # the latest rolling window for a historical launch result.
            launch_window = read_window(start_date, launch_end, launch_days)
    if rule_version > 0:
        candidate = compute_launch_result(
            metrics=launch_window,
            rules=rules,
            start_date=start_date,
            as_of=end,
        )
        # A saved draft rule version does not establish business approval.
        # Never publish a definitive success/failure from candidate thresholds.
        result["launch"] = (
            {"status": "awaiting_approved_rules", "result": None}
            if candidate["status"] == "evaluated"
            else candidate
        )
    else:
        result["launch"] = {"status": "awaiting_approved_rules", "result": None}
    return result
