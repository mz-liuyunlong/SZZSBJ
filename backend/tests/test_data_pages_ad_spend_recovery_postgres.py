"""PostgreSQL transaction integration coverage for SP-only financial recovery."""

import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_ad_spend_recovery import (
    recover_standard_ad_spend,
)


@pytest.mark.integration
def test_postgres_sp_recovery_is_idempotent_and_excludes_unsold_items():
    url = os.getenv("AD_SP_RECOVERY_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("AD_SP_RECOVERY_TEST_POSTGRES_URL not configured")
    engine = create_engine(url)
    day = date(2026, 10, 29)
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(
                    text(
                        "create temp table mart_daily_sales_item_day ("
                        "id integer primary key,source_account_ref text,"
                        "business_date_la date,store_id text,item_id text,msku text,"
                        "local_sku text,sales_amount numeric,ad_spend_amount numeric,"
                        "ad_ratio numeric,updated_at timestamptz)"
                    )
                )
                conn.execute(
                    text(
                        "create temp table fact_walmart_ad_item_sp_daily ("
                        "source_account_ref text,business_date_la date,"
                        "store_id text,item_id text,msku text,ad_spend_amount numeric)"
                    )
                )
                conn.execute(
                    text(
                        "create temp table mart_order_profit_sku_day ("
                        "source_account_ref text,business_date_la date,"
                        "local_sku text,ad_spend_amount numeric,updated_at timestamptz)"
                    )
                )
                conn.execute(
                    text(
                        "insert into mart_daily_sales_item_day "
                        "values (1,'account',:day,'store','item','SKU','SKU',"
                        "100,0,null,now())"
                    ),
                    {"day": day},
                )
                conn.execute(
                    text(
                        "insert into fact_walmart_ad_item_sp_daily values "
                        "('account',:day,'store','item','SKU',8.50),"
                        "('account',:day,'store','unsold','UNSOLD',1.50)"
                    ),
                    {"day": day},
                )
                conn.execute(
                    text(
                        "insert into mart_order_profit_sku_day "
                        "values ('account',:day,'SKU',0,now())"
                    ),
                    {"day": day},
                )
                with Session(bind=conn) as session:
                    assert recover_standard_ad_spend(session, "account", day) == Decimal("8.50")
                    assert recover_standard_ad_spend(session, "account", day) == Decimal("8.50")
                rows = conn.execute(
                    text("select ad_spend_amount,ad_ratio from mart_daily_sales_item_day")
                ).one()
                assert rows == (Decimal("8.50"), Decimal("0.085"))
                profit = conn.execute(
                    text("select ad_spend_amount from mart_order_profit_sku_day")
                ).scalar_one()
                assert profit == Decimal("8.50")
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
