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

    # Preserve every non-advertising financial input and all existing profit
    # calculation rules. Update only the rollup field derived from Daily Sales.
    session.execute(
        text(
            "with totals as (select coalesce(nullif(local_sku,''),item_id) sku,"
            "sum(coalesce(ad_spend_amount,0)) spend "
            "from mart_daily_sales_item_day "
            "where source_account_ref=:account and business_date_la=:day "
            "group by 1) "
            "update mart_order_profit_sku_day p set "
            "ad_spend_amount=t.spend,updated_at=now() "
            "from totals t where p.source_account_ref=:account "
            "and p.business_date_la=:day and p.local_sku=t.sku "
            "and p.ad_spend_amount is distinct from t.spend"
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
