"""Run against the disposable CI PostgreSQL database, never production."""

import ast
import inspect
import json
import os
import textwrap
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_test_database_url
from app.modules.integration_sync.data_pages_business_rules_v2 import DataPagesRealSyncRunner


@pytest.mark.skipif(
    os.getenv("WALMART_ORDER_IDENTITY_DB_TESTS") != "1",
    reason="CI-only isolated PostgreSQL integration test",
)
def test_sem_only_multi_msku_and_account_scoping_postgresql() -> None:
    """Execute the exact MART CTE against an isolated PostgreSQL connection."""
    url = get_test_database_url(Settings())
    parsed = urlparse(
        url.render_as_string(hide_password=False).replace("postgresql+psycopg", "postgresql")
    )
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path == "/walmart_order_identity_test"

    method_source = textwrap.dedent(
        inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)
    )
    tree = ast.parse(method_source)
    statements = [
        call.args[0].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "text"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ]
    target = next(
        statement
        for statement in statements
        if "with s as (" in statement and "insert into mart_daily_sales_item_day" in statement
    )
    ctes = target.split("insert into mart_daily_sales_item_day", 1)[0]
    query = ctes + (
        "select k.store_id,k.item_id,k.msku,coalesce(sem.sem_ad_spend,0) sem_spend "
        "from k left join sem_resolved sem on sem.sem_date=k.business_date_la "
        "and sem.store_id=k.store_id and sem.item_id=k.item_id and sem.msku=k.msku "
        "order by k.store_id,k.item_id,k.msku"
    )

    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                # TEMP tables shadow public tables for this one connection.
                conn.exec_driver_sql(
                    "create temporary table fact_walmart_sales_item_daily ("
                    "business_date_la date,source_account_ref text,store_id text,item_id text,"
                    "msku text,local_sku text,product_name text,sales_qty numeric,"
                    "order_count numeric,sales_amount numeric,sales_currency_code text,"
                    "allocation_status text)"
                )
                conn.exec_driver_sql(
                    "create temporary table fact_walmart_ad_item_sp_daily ("
                    "business_date_la date,source_account_ref text,store_id text,item_id text,"
                    "msku text,ad_spend_amount numeric)"
                )
                conn.exec_driver_sql(
                    "create temporary table after_sales_refund_items ("
                    "source_account_ref text,platform_code text,refund_effective boolean,"
                    "purchase_time_at timestamp,store_id text,item_id text,msku text,"
                    "local_sku text,return_qty numeric,refund_amount numeric)"
                )
                conn.exec_driver_sql(
                    "create temporary table fact_walmart_sample_order_items ("
                    "source_account_ref text,business_date_utc_minus_7 date,store_id text,"
                    "item_id text,msku text,local_sku text,platform_order_no text,"
                    "quantity numeric,unit_price_amount numeric,is_valid_sample boolean,"
                    "sample_rule_version text)"
                )
                conn.exec_driver_sql(
                    "create temporary table dim_walmart_listings ("
                    "source_account_ref text,store_id text,item_id text,msku text)"
                )
                conn.execute(
                    text("insert into dim_walmart_listings values (:account,:store,:item,:msku)"),
                    [
                        {
                            "account": "account-a",
                            "store": "store-a",
                            "item": "12345678901",
                            "msku": "M1",
                        },
                        {
                            "account": "account-a",
                            "store": "store-a",
                            "item": "12345678902",
                            "msku": "M2",
                        },
                        {
                            "account": "account-b",
                            "store": "store-b",
                            "item": "12345678903",
                            "msku": "M3",
                        },
                    ],
                )
                # A historical MSKU is retained in Sales, but SEM must hit M2 only.
                conn.execute(
                    text(
                        "insert into fact_walmart_sales_item_daily "
                        "(business_date_la,source_account_ref,store_id,item_id,msku,"
                        "allocation_status,sales_qty,order_count,sales_amount) "
                        "values (:day,:account,:store,:item,:msku,'direct',1,1,10)"
                    ),
                    {
                        "day": date(2026, 10, 19),
                        "account": "account-a",
                        "store": "store-a",
                        "item": "12345678902",
                        "msku": "M2-old",
                    },
                )

                items = [
                    (-1001, "store-a", "prior", "older", "12345678901", "9.00", 10),
                    (-1002, "store-a", "current", "latest-one", "12345678901", "4.00", 11),
                    (-1003, "store-a", "current", "latest-two", "12345678902", "3.00", 11),
                    (-1004, "store-b", "other", "other-store", "12345678903", "5.00", 11),
                ]
                for n, (id_, store, task, campaign, item, spend, hour) in enumerate(items):
                    conn.execute(
                        text(
                            "insert into legacy_mirror.raw_walmart_sem_csv "
                            "(id,task_id,row_index,csv_type,row_json,report_date,store_id,"
                            "raw_hash,created_at) values "
                            "(:id,:task,:row_no,'sem_daily',cast(:raw as jsonb),"
                            "'2026-10-19',:store,:hash,:created)"
                        ),
                        {
                            "id": id_,
                            "task": task,
                            "row_no": n,
                            "store": store,
                            "hash": f"{'a' * 63}{n}",
                            "created": datetime(2026, 10, 19, hour),
                            "raw": json.dumps(
                                {
                                    "Date": "2026-10-19",
                                    "Campaign ID": campaign,
                                    "Campaign Name": f"synthetic-{item}",
                                    "Spend": spend,
                                }
                            ),
                        },
                    )
                result = (
                    conn.execute(
                        text(query),
                        {
                            "account": "account-a",
                            "day": date(2026, 10, 19),
                            "historical_sample_rule_version": (
                                "zero-total-provider-status-strict-triple-v3"
                            ),
                            "verified_sample_rule_version": "provider-verified-sample-v5",
                        },
                    )
                    .mappings()
                    .all()
                )
                amounts = {
                    (r["store_id"], r["item_id"], r["msku"]): Decimal(r["sem_spend"])
                    for r in result
                }
                assert amounts == {
                    ("store-a", "12345678901", "M1"): Decimal("4.00"),
                    ("store-a", "12345678902", "M2"): Decimal("3.00"),
                    ("store-a", "12345678902", "M2-old"): Decimal("0"),
                }
                assert sum(amounts.values()) == Decimal("7.00")
            finally:
                tx.rollback()
    finally:
        engine.dispose()
