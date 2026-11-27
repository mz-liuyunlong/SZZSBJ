"""Recover validated SP advertising costs when independent SEM reconciliation blocks MART.

This is a narrow, idempotent repair of existing Daily Sales rows. It never
creates sales rows or allocates spend to items without a sales row.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session


def recover_standard_ad_spend(session: Session, account: str, day) -> Decimal:
    """Reconcile standard SP spend to existing Daily Sales and Order Profit rows.

    Caller must have rolled back the failed financial transaction first.
    Any SQL failure must roll back the entire recovery transaction.
    """
    params = {"account": account, "day": day}
    # Refuse ambiguous MART identities: joining to multiple rows would duplicate spend.
    duplicate_keys = session.execute(
        text(
            "select count(*) from (select store_id,item_id,trim(msku) msku "
            "from mart_daily_sales_item_day "
            "where source_account_ref=:account and business_date_la=:day "
            "group by 1,2,3 having count(*)>1) duplicates"
        ),
        params,
    ).scalar_one()
    if duplicate_keys:
        raise ValueError("DATA_PAGES_SP_RECOVERY_DUPLICATE_MART_KEYS")

    # Do not repair a date for which no Daily Sales result exists yet.
    mart_count = session.execute(
        text(
            "select count(*) from mart_daily_sales_item_day "
            "where source_account_ref=:account and business_date_la=:day"
        ),
        params,
    ).scalar_one()
    if not mart_count:
        raise ValueError("DATA_PAGES_SP_RECOVERY_MART_MISSING")

    source_count = session.execute(
        text(
            "select count(*) from fact_walmart_ad_item_sp_daily "
            "where source_account_ref=:account and business_date_la=:day"
        ),
        params,
    ).scalar_one()
    if not source_count:
        raise ValueError("DATA_PAGES_SP_RECOVERY_SOURCE_MISSING")

    # Source facts and their normalized keys are authoritative. Mismatched or
    # no-sale ads stay in the fact table, never redistributed to other items.
    session.execute(
        text(
            "with ads as (select store_id,item_id,trim(msku) msku,"
            "sum(coalesce(ad_spend_amount,0)) spend "
            "from fact_walmart_ad_item_sp_daily "
            "where source_account_ref=:account and business_date_la=:day "
            "and store_id is not null and item_id is not null "
            "and nullif(trim(msku),'') is not null group by 1,2,3),"
            "expected as (select m.id,coalesce(a.spend,0) spend "
            "from mart_daily_sales_item_day m left join ads a "
            "on a.store_id=m.store_id and a.item_id=m.item_id "
            "and a.msku=trim(m.msku) "
            "where m.source_account_ref=:account and m.business_date_la=:day) "
            "update mart_daily_sales_item_day m set "
            "ad_spend_amount=e.spend,"
            "ad_ratio=case when m.sales_amount>0 then e.spend/m.sales_amount else null end,"
            "updated_at=now() "
            "from expected e where m.id=e.id "
            "and (m.ad_spend_amount is distinct from e.spend "
            "or m.ad_ratio is distinct from "
            "(case when m.sales_amount>0 then e.spend/m.sales_amount else null end))"
        ),
        params,
    )

    # SEM may still be unattributed, but the already-booked SP costs and
    # financial results must not contradict one another. Recompute from the
    # current expense columns, never by subtracting the SP delta from an old
    # profit (which might itself already be stale).
    session.execute(
        text(
            """
            WITH base AS (
                SELECT id, sales_amount,
                       purchase_cost_total_usd + first_leg_cost_total_usd AS invested,
                       CASE
                           WHEN refund_amount IS NOT NULL
                            AND commission_fee_amount IS NOT NULL
                            AND purchase_cost_total_usd IS NOT NULL
                            AND first_leg_cost_total_usd IS NOT NULL
                            AND wfs_fee_total_amount IS NOT NULL
                            AND storage_fee_total_amount IS NOT NULL
                           THEN sales_amount
                                - COALESCE(ad_spend_amount, 0)
                                - COALESCE(sem_ad_spend_amount, 0)
                                - refund_amount
                                - commission_fee_amount
                                - purchase_cost_total_usd
                                - first_leg_cost_total_usd
                                - wfs_fee_total_amount
                                - storage_fee_total_amount
                       END AS profit
                FROM mart_daily_sales_item_day
                WHERE source_account_ref = :account
                  AND business_date_la = :day
            ), expected AS (
                SELECT id, profit::numeric(18,4) AS profit,
                       CASE WHEN profit IS NOT NULL AND sales_amount > 0
                            THEN (profit / sales_amount)::numeric(18,6)
                       END AS margin,
                       CASE WHEN profit IS NOT NULL AND invested > 0
                            THEN (profit / invested)::numeric(18,6)
                       END AS roi
                FROM base
            )
            UPDATE mart_daily_sales_item_day AS m
            SET gross_profit_amount = e.profit,
                gross_margin = e.margin,
                roi = e.roi,
                updated_at = now()
            FROM expected AS e
            WHERE m.id = e.id
              AND (m.gross_profit_amount, m.gross_margin, m.roi)
                  IS DISTINCT FROM (e.profit, e.margin, e.roi)
            """
        ),
        params,
    )

    # Roll up the now-consistent Daily Sales financials using the same SKU
    # grouping and NULL-profit semantics as the normal MART refresh.
    session.execute(
        text(
            """
            WITH totals AS (
                SELECT COALESCE(NULLIF(local_sku, ''), item_id) AS sku,
                       SUM(COALESCE(ad_spend_amount, 0)) AS spend,
                       CASE WHEN BOOL_AND(gross_profit_amount IS NOT NULL)
                            THEN SUM(gross_profit_amount)
                       END AS profit,
                       SUM(sales_amount) AS sales,
                       SUM(
                           COALESCE(purchase_cost_total_usd, 0)
                           + COALESCE(first_leg_cost_total_usd, 0)
                       ) AS invested
                FROM mart_daily_sales_item_day
                WHERE source_account_ref = :account
                  AND business_date_la = :day
                GROUP BY 1
            ), expected AS (
                SELECT sku, spend, profit,
                       CASE WHEN profit IS NOT NULL AND sales > 0
                            THEN (profit / sales)::numeric(18,6)
                       END AS margin,
                       CASE WHEN profit IS NOT NULL AND invested > 0
                            THEN (profit / invested)::numeric(18,6)
                       END AS roi
                FROM totals
            )
            UPDATE mart_order_profit_sku_day AS p
            SET ad_spend_amount = e.spend,
                gross_profit_amount = e.profit,
                gross_margin = e.margin,
                roi = e.roi,
                updated_at = now()
            FROM expected AS e
            WHERE p.source_account_ref = :account
              AND p.business_date_la = :day
              AND p.local_sku = e.sku
              AND (p.ad_spend_amount, p.gross_profit_amount, p.gross_margin, p.roi)
                  IS DISTINCT FROM (e.spend, e.profit, e.margin, e.roi)
            """
        ),
        params,
    )

    daily_spend, profit_spend = session.execute(
        text(
            "select "
            "(select coalesce(sum(ad_spend_amount),0) "
            "from mart_daily_sales_item_day "
            "where source_account_ref=:account and business_date_la=:day),"
            "(select coalesce(sum(ad_spend_amount),0) "
            "from mart_order_profit_sku_day "
            "where source_account_ref=:account and business_date_la=:day)"
        ),
        params,
    ).one()
    if Decimal(str(daily_spend)) != Decimal(str(profit_spend)):
        raise ValueError("DATA_PAGES_SP_RECOVERY_PROFIT_ROLLUP_MISMATCH")
    return Decimal(str(daily_spend))
