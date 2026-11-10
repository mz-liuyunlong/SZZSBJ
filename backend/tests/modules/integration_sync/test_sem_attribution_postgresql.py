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


@pytest.mark.skipif(
    os.getenv("WALMART_ORDER_IDENTITY_DB_TESTS") != "1",
    reason="CI-only isolated PostgreSQL integration test",
)
def test_finance_sem_reserve_postgresql_replay_account_and_transaction_isolation() -> None:
    """Exercise reserve SQL against disposable PostgreSQL; roll back every fixture."""
    from sqlalchemy.orm import Session

    from app.modules.integration_sync.data_pages_finance_partial_isolation import (
        reserve_unallocated_sem_lines,
    )

    url = get_test_database_url(Settings())
    parsed = urlparse(
        url.render_as_string(hide_password=False).replace("postgresql+psycopg", "postgresql")
    )
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path == "/walmart_order_identity_test"

    engine = create_engine(url, hide_parameters=True)
    day = date(2026, 10, 19)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                connection.exec_driver_sql(
                    "create temporary table dim_walmart_listings ("
                    "source_account_ref text,store_id text,item_id text,msku text)"
                )
                connection.exec_driver_sql(
                    "create temporary table dim_lingxing_stores ("
                    "source_account_ref text,store_id text)"
                )
                connection.exec_driver_sql(
                    "create temporary table biz_finance_unallocated_sem_lines ("
                    "id uuid primary key,source_account_ref text not null,"
                    "business_date_la date not null,store_id text not null,task_id text not null,"
                    "row_index integer not null,raw_hash text,campaign_id text,candidate_item_id text,"
                    "spend_amount_usd numeric(18,4) not null,reason_code text not null,"
                    "status text not null,is_current boolean not null,owner_note text,"
                    "resolved_by text,resolved_at timestamptz,created_at timestamptz not null,"
                    "last_seen_at timestamptz not null,"
                    "unique(source_account_ref,business_date_la,store_id,task_id,row_index))"
                )
                connection.execute(
                    text(
                        "insert into dim_walmart_listings values "
                        "('account-a','store-a','12345678901','M1'),"
                        "('account-a','store-a','12345678902','M2-A'),"
                        "('account-a','store-a','12345678902','M2-B'),"
                        "('account-b','store-b','12345678903','M3')"
                    )
                )

                def add_raw(
                    row_id: int,
                    task: str,
                    row_index: int,
                    store: str,
                    spend: str,
                    campaign_id: str,
                    campaign_name: str,
                    created_hour: int,
                    report_day: date = day,
                ) -> None:
                    connection.execute(
                        text(
                            "insert into legacy_mirror.raw_walmart_sem_csv "
                            "(id,task_id,row_index,csv_type,row_json,report_date,store_id,raw_hash,created_at) "
                            "values (:id,:task,:row_index,'sem_daily',cast(:raw as jsonb),"
                            ":report_day,:store,:hash,:created)"
                        ),
                        {
                            "id": row_id,
                            "task": task,
                            "row_index": row_index,
                            "store": store,
                            "report_day": report_day,
                            "hash": f"{row_id:064d}",
                            "created": datetime.combine(report_day, datetime.min.time()).replace(
                                hour=created_hour
                            ),
                            "raw": json.dumps(
                                {
                                    "Date": report_day.isoformat(),
                                    "Campaign ID": campaign_id,
                                    "Campaign Name": campaign_name,
                                    "Spend": spend,
                                }
                            ),
                        },
                    )

                add_raw(
                    -9101, "task-old", 0, "store-a", "99.00", "old-campaign", "old 12345678901", 1
                )
                add_raw(
                    -9102,
                    "task-latest",
                    0,
                    "store-a",
                    "4.00",
                    "resolved",
                    "resolved 12345678901",
                    2,
                )
                add_raw(
                    -9103,
                    "task-latest",
                    1,
                    "store-a",
                    "16.29",
                    "unresolved",
                    "campaign without an item identity",
                    2,
                )
                add_raw(
                    -9104,
                    "task-latest",
                    2,
                    "store-a",
                    "2.00",
                    "ambiguous",
                    "ambiguous 12345678902",
                    2,
                )
                add_raw(
                    -9105, "task-latest", 3, "store-a", "-1.00", "credit", "credit 12345678901", 2
                )
                add_raw(
                    -9106,
                    "task-other-account",
                    0,
                    "store-b",
                    "7.00",
                    "other",
                    "other 12345678903",
                    2,
                )

                with Session(bind=connection) as session:
                    reserved = reserve_unallocated_sem_lines(
                        session, source_account_ref="account-a", business_date=day
                    )
                    assert reserved == Decimal("17.29")
                    current = session.execute(
                        text(
                            "select count(*),sum(spend_amount_usd),"
                            "array_agg(reason_code order by row_index) "
                            "from biz_finance_unallocated_sem_lines where is_current=true"
                        )
                    ).one()
                    assert current[0] == 3
                    assert current[1] == Decimal("17.2900")
                    assert set(current[2]) == {
                        "ITEM_ID_UNRESOLVED",
                        "LISTING_IDENTITY_AMBIGUOUS",
                        "NEGATIVE_CREDIT_REVIEW",
                    }
                    assert (
                        session.execute(
                            text(
                                "select count(*) from biz_finance_unallocated_sem_lines "
                                "where store_id='store-b'"
                            )
                        ).scalar_one()
                        == 0
                    )

                    # Replaying the same task is idempotent.
                    assert reserve_unallocated_sem_lines(
                        session, source_account_ref="account-a", business_date=day
                    ) == Decimal("17.29")
                    assert (
                        session.execute(
                            text("select count(*) from biz_finance_unallocated_sem_lines")
                        ).scalar_one()
                        == 3
                    )

                    # A newer task supersedes current rows but preserves prior evidence.
                    add_raw(
                        -9107,
                        "task-newest",
                        0,
                        "store-a",
                        "5.00",
                        "new-unresolved",
                        "new task unresolved",
                        3,
                    )
                    assert reserve_unallocated_sem_lines(
                        session, source_account_ref="account-a", business_date=day
                    ) == Decimal("5.00")
                    assert session.execute(
                        text(
                            "select count(*),sum(spend_amount_usd) "
                            "from biz_finance_unallocated_sem_lines where is_current=true"
                        )
                    ).one() == (1, Decimal("5.0000"))
                    assert (
                        session.execute(
                            text("select count(*) from biz_finance_unallocated_sem_lines")
                        ).scalar_one()
                        == 4
                    )

                    # Roll back a separate business day without affecting the prior day.
                    nested = session.begin_nested()
                    next_day = date(2026, 10, 20)
                    add_raw(
                        -9108,
                        "task-next-day",
                        0,
                        "store-a",
                        "8.00",
                        "next-day",
                        "next day unresolved",
                        4,
                        report_day=next_day,
                    )
                    assert reserve_unallocated_sem_lines(
                        session, source_account_ref="account-a", business_date=next_day
                    ) == Decimal("8.00")
                    nested.rollback()
                    assert (
                        session.execute(
                            text(
                                "select count(*) from biz_finance_unallocated_sem_lines "
                                "where business_date_la=:day"
                            ),
                            {"day": next_day},
                        ).scalar_one()
                        == 0
                    )
                    assert session.execute(
                        text(
                            "select count(*),sum(spend_amount_usd) "
                            "from biz_finance_unallocated_sem_lines "
                            "where business_date_la=:day and is_current=true"
                        ),
                        {"day": day},
                    ).one() == (1, Decimal("5.0000"))
            finally:
                outer.rollback()
    finally:
        engine.dispose()


def test_disputed_sample_does_not_reduce_gross_mart_quantities_or_amounts() -> None:
    """MART SQL must preserve gross SaleStat facts when sample evidence conflicts."""
    source = textwrap.dedent(inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart))
    tree = ast.parse(source)
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
    mart_sql = next(
        statement
        for statement in statements
        if "insert into mart_daily_sales_item_day" in statement
    )
    assert "sample_checked as" in mart_sql
    assert (
        "case when coalesce(sample.sample_disputed,false) then coalesce(s.sales_qty,0)" in mart_sql
    )
    assert (
        "case when coalesce(sample.sample_disputed,false) then coalesce(s.sales_amount,0)"
        in mart_sql
    )
    assert "left join sample_checked sample" in mart_sql
    assert "case when coalesce(sample.sample_disputed,false) then null" in mart_sql
