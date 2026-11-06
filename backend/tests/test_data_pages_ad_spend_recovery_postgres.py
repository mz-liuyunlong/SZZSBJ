"""PostgreSQL integration coverage for SP recovery and financial consistency."""

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
def test_sp_recovery_recalculates_profit_roi_and_multi_store_rollup_idempotently():
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
                        "local_sku text,sales_amount numeric,refund_amount numeric,"
                        "ad_spend_amount numeric,sem_ad_spend_amount numeric,"
                        "ad_ratio numeric,commission_fee_amount numeric,"
                        "wfs_fee_total_amount numeric,purchase_cost_total_usd numeric,"
                        "first_leg_cost_total_usd numeric,storage_fee_total_amount numeric,"
                        "gross_profit_amount numeric,gross_margin numeric,roi numeric,"
                        "updated_at timestamptz)"
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
                        "local_sku text,ad_spend_amount numeric,"
                        "gross_profit_amount numeric,gross_margin numeric,"
                        "roi numeric,updated_at timestamptz)"
                    )
                )
                conn.execute(
                    text(
                        "insert into mart_daily_sales_item_day values "
                        "(1,'account',:day,'store1','item1','MSKU1','SKU',"
                        "12.99,0,14.91,0,null,1.5588,3.45,1.7273,1.0909,"
                        "0.0032,5.1598,0.397215,1.830903,now()),"
                        "(2,'account',:day,'store2','item2','MSKU2','SKU',"
                        "20,0,0,0,null,2,3,2,1,0,12,0.6,4,now()),"
                        "(3,'account',:day,'store3','item3','MSKU3','ZERO',"
                        "0,0,0,0,null,0,0,0,0,0,0,null,null,now()),"
                        "(4,'account',:day,'store4','item4','MSKU4','MISSING',"
                        "10,0,0,0,null,1,2,null,1,0,null,null,null,now())"
                    ),
                    {"day": day},
                )
                conn.execute(
                    text(
                        "insert into fact_walmart_ad_item_sp_daily values "
                        "('account',:day,'store1','item1','MSKU1',7.57),"
                        "('account',:day,'store1','item1','MSKU1',7.34),"
                        "('account',:day,'store2','item2','MSKU2',2.5),"
                        "('account',:day,'store3','item3','MSKU3',1.5),"
                        "('account',:day,'store9','unsold','UNSOLD',5)"
                    ),
                    {"day": day},
                )
                conn.execute(
                    text(
                        "insert into mart_order_profit_sku_day values "
                        "('account',:day,'SKU',0,17.1598,0.52015,3.146,"
                        "now()),"
                        "('account',:day,'ZERO',0,0,null,null,now()),"
                        "('account',:day,'MISSING',0,null,null,null,now())"
                    ),
                    {"day": day},
                )
                with Session(bind=conn) as session:
                    assert recover_standard_ad_spend(session, "account", day) == Decimal(
                        "18.91"
                    )
                    first = conn.execute(
                        text(
                            "select id,ad_spend_amount,gross_profit_amount,"
                            "gross_margin,roi from mart_daily_sales_item_day "
                            "order by id"
                        )
                    ).all()
                    sku_first = conn.execute(
                        text(
                            "select local_sku,ad_spend_amount,gross_profit_amount,"
                            "gross_margin,roi from mart_order_profit_sku_day "
                            "order by local_sku"
                        )
                    ).all()
                    assert recover_standard_ad_spend(session, "account", day) == Decimal(
                        "18.91"
                    )
                    assert first == conn.execute(
                        text(
                            "select id,ad_spend_amount,gross_profit_amount,"
                            "gross_margin,roi from mart_daily_sales_item_day "
                            "order by id"
                        )
                    ).all()
                    assert sku_first == conn.execute(
                        text(
                            "select local_sku,ad_spend_amount,gross_profit_amount,"
                            "gross_margin,roi from mart_order_profit_sku_day "
                            "order by local_sku"
                        )
                    ).all()

                rows = {row[0]: row for row in first}
                assert rows[1][1] == Decimal("14.91")
                assert rows[1][2] == Decimal("-9.7502")
                assert rows[1][3].quantize(Decimal("0.000001")) == Decimal("-0.750593")
                assert rows[1][4].quantize(Decimal("0.000001")) == Decimal("-3.459421")
                assert rows[2][1] == Decimal("2.5")
                assert rows[2][2] == Decimal("9.5")
                assert rows[3][1] == Decimal("1.5")
                assert rows[3][2] == Decimal("-1.5")
                assert rows[3][3] is None
                assert rows[3][4] is None
                assert rows[4][1] == Decimal("0")
                assert rows[4][2] is None

                sku = {row[0]: row for row in sku_first}
                assert sku["SKU"][1] == Decimal("17.41")
                assert sku["SKU"][2] == Decimal("-0.2502")
                assert sku["ZERO"][2] == Decimal("-1.5")
                assert sku["MISSING"][2] is None
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_sp_recovery_rejects_missing_profit_rollup_and_rollback_is_atomic():
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
                        "local_sku text,sales_amount numeric,refund_amount numeric,"
                        "ad_spend_amount numeric,sem_ad_spend_amount numeric,"
                        "ad_ratio numeric,commission_fee_amount numeric,"
                        "wfs_fee_total_amount numeric,purchase_cost_total_usd numeric,"
                        "first_leg_cost_total_usd numeric,storage_fee_total_amount numeric,"
                        "gross_profit_amount numeric,gross_margin numeric,roi numeric,"
                        "updated_at timestamptz)"
                    )
                )
                conn.execute(
                    text(
                        "create temp table fact_walmart_ad_item_sp_daily ("
                        "source_account_ref text,business_date_la date,"
                        "store_id text,item_id text,msku text,ad_spend_amount numeric)"
                    )
                )
                # Intentionally absent mart_order_profit_sku_day: recovery must fail
                # after the daily update and roll back on the caller's transaction.
                conn.execute(
                    text(
                        "insert into mart_daily_sales_item_day values "
                        "(1,'account',:day,'s','i','MSKU','SKU',"
                        "10,0,0,0,null,1,1,1,1,0,7,0.7,3.5,now())"
                    ),
                    {"day": day},
                )
                conn.execute(
                    text(
                        "insert into fact_walmart_ad_item_sp_daily values "
                        "('account',:day,'s','i','MSKU',3)"
                    ),
                    {"day": day},
                )
                savepoint = conn.begin_nested()
                try:
                    with Session(bind=conn) as session:
                        with pytest.raises(Exception):
                            recover_standard_ad_spend(session, "account", day)
                finally:
                    savepoint.rollback()

                row = conn.execute(
                    text(
                        "select ad_spend_amount,gross_profit_amount "
                        "from mart_daily_sales_item_day where id=1"
                    )
                ).one()
                assert row == (Decimal("0"), Decimal("7"))
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
