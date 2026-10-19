"""Real PostgreSQL 16 regression: same-account operation log owner isolation.

Runs only in the disposable opslog_ci GitHub Actions service, never against an
application database. All synthetic writes are covered by an outer rollback.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.config import get_database_url
from app.modules.operation_logs.access import LogAccess, require_owned_identity
from app.modules.operation_logs.daily_sales import load_daily_sales_log_summaries
from app.modules.operation_logs.router import get_logs
from app.modules.operation_logs.rows_router import get_rows
from app.modules.operation_logs.service import _import_batch, save_batch, save_link

ACCOUNT = "synthetic-account"
STORE = "synthetic-store"
DAY = date(2026, 10, 17)
A_ID, B_ID = 9227001, 9227002


@pytest.fixture
def pg_session() -> Iterator[Session]:
    if os.getenv("CI") != "true" or os.getenv("OPERATION_LOG_POSTGRES_TESTS") != "1":
        pytest.skip("requires isolated CI PostgreSQL and explicit opt-in")
    if os.getenv("APP_ENV") != "dev":
        pytest.fail("unexpected PostgreSQL environment", pytrace=False)
    url = get_database_url()
    if (
        url.host != "127.0.0.1"
        or url.database != "opslog_ci"
        or url.username != "opslog_ci"
        or url.query
    ):
        pytest.fail("refusing unexpected database target", pytrace=False)
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("select current_database(), current_user, host(inet_server_addr())")
            ).one()
            # A GitHub Actions service container normally exposes a bridge
            # interface even when the client dials 127.0.0.1 on the runner.
            # The ephemeral CI opt-in, strict URL, database and username checks
            # above protect against executing this suite on an app database.
            if row[0] != "opslog_ci" or row[1] != "opslog_ci" or not row[2]:
                pytest.fail("unexpected PostgreSQL server identity", pytrace=False)
            transaction = conn.begin_nested()
            try:
                for ddl in (
                    "create temporary table mart_listing_management_current "
                    "(source_account_ref text, store_id text, store_name text, item_id text, "
                    "msku text, local_sku text, title text, owner_ref text, sale_price_amount "
                    "numeric) on commit preserve rows",
                    "create temporary table mart_daily_sales_item_day (source_account_ref "
                    "text, store_id text, item_id text, msku text, local_sku text, "
                    "business_date_la date) on commit preserve rows",
                    "create temporary table dwd_lingxing_sku_product_info_current "
                    "(source_account_ref text, lingxing_sku_code text, owner_uid text) on "
                    "commit preserve rows",
                ):
                    conn.execute(text(ddl))
                conn.execute(
                    text(
                        "insert into app_users (id, username, display_name, password_hash, is_active) values "
                        "(:a, 'synthetic_a', 'A', 'ci-nonlogin-test-only', 1), (:b, 'synthetic_b', 'B', 'ci-nonlogin-test-only', 1)"
                    ),
                    {"a": A_ID, "b": B_ID},
                )
                conn.execute(
                    text(
                        "insert into ops_lingxing_owner_user_mappings (source_account_ref, "
                        "owner_uid, app_user_id) "
                        "values (:account, 'uid-a', :a), (:account, 'uid-b', :b)"
                    ),
                    {"account": ACCOUNT, "a": A_ID, "b": B_ID},
                )
                conn.execute(
                    text(
                        "insert into dwd_lingxing_sku_product_info_current (source_account_ref, "
                        "lingxing_sku_code, owner_uid) "
                        "values (:account, 'sku-a', 'uid-a'), (:account, 'sku-b', 'uid-b')"
                    ),
                    {"account": ACCOUNT},
                )
                conn.execute(
                    text(
                        "insert into mart_listing_management_current "
                        "(source_account_ref, store_id, store_name, item_id, msku, local_sku, "
                        "title, owner_ref, sale_price_amount) "
                        "values (:account, :store, 'Store', 'item-a', 'msku-a', 'sku-a', 'A', "
                        "'A', 10), "
                        "(:account, :store, 'Store', 'item-b', 'msku-b', 'sku-b', 'B', 'B', 20)"
                    ),
                    {"account": ACCOUNT, "store": STORE},
                )
                conn.execute(
                    text(
                        "insert into mart_daily_sales_item_day "
                        "(source_account_ref, store_id, item_id, msku, local_sku, "
                        "business_date_la) "
                        "values (:account, :store, 'item-a', 'msku-a', 'sku-a', :day), "
                        "(:account, :store, 'item-b', 'msku-b', 'sku-b', :day)"
                    ),
                    {"account": ACCOUNT, "store": STORE, "day": DAY},
                )
                with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def access(user: int) -> LogAccess:
    return LogAccess(
        user_id=user, accounts=frozenset({ACCOUNT}), is_admin=False, display_name="Test"
    )


def identity(which: str) -> dict:
    return dict(account=ACCOUNT, day=DAY, store=STORE, item=f"item-{which}", msku=f"msku-{which}")


def log_row(which: str) -> dict:
    return {
        **identity(which),
        "content": f"note-{which}",
        "work_type": "其他",
        "work_types": ["其他"],
        "observe_days": None,
        "status": "submitted",
        "revision": 0,
    }


def request(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


def test_same_account_users_cannot_read_write_or_link_other_owner(pg_session: Session) -> None:
    alice, bob = access(A_ID), access(B_ID)
    for caller, owns, forbidden in ((alice, "a", "b"), (bob, "b", "a")):
        require_owned_identity(pg_session, caller, **identity(owns))
        with pytest.raises(ApiError) as error:
            require_owned_identity(pg_session, caller, **identity(forbidden))
        assert error.value.status_code == 403

    assert save_batch(
        pg_session, accounts=alice.accounts, rows=[log_row("a")], actor=str(A_ID), access=alice
    ) == [1]
    assert save_batch(
        pg_session, accounts=bob.accounts, rows=[log_row("b")], actor=str(B_ID), access=bob
    ) == [1]
    with pytest.raises(ApiError) as error:
        save_batch(
            pg_session, accounts=bob.accounts, rows=[log_row("a")], actor=str(B_ID), access=bob
        )
    assert error.value.status_code == 403

    for caller, own, other in ((alice, "a", "b"), (bob, "b", "a")):
        listing = get_rows(
            request=request("/api/operations/logs/rows"),
            session=pg_session,
            _=None,
            accounts=caller.accounts,
            access=caller,
            start_date=DAY,
            end_date=DAY,
        ).data
        assert {row["productId"] for row in listing["rows"]} == {f"item-{own}"}
        detail = get_logs(
            request=request("/api/operations/logs"),
            session=pg_session,
            _=None,
            accounts=caller.accounts,
            access=caller,
            **identity(own),
        ).data
        assert detail["operation_log"] == f"note-{own}"
        with pytest.raises(ApiError) as error:
            get_logs(
                request=request("/api/operations/logs"),
                session=pg_session,
                _=None,
                accounts=caller.accounts,
                access=caller,
                **identity(other),
            )
        assert error.value.status_code == 403

    save_link(
        pg_session,
        accounts=alice.accounts,
        account=ACCOUNT,
        store=STORE,
        item="item-a",
        msku="msku-a",
        entry_type="keyword",
        name="Link",
        url="/ads/keyword-library",
        note="",
        actor=str(A_ID),
        access=alice,
    )
    with pytest.raises(ApiError) as error:
        save_link(
            pg_session,
            accounts=bob.accounts,
            account=ACCOUNT,
            store=STORE,
            item="item-a",
            msku="msku-a",
            entry_type="keyword",
            name="No",
            url="/ads/keyword-library",
            note="",
            actor=str(B_ID),
            access=bob,
        )
    assert error.value.status_code == 403

    sales = [
        SimpleNamespace(
            business_date_la=DAY,
            source_account_ref=ACCOUNT,
            store_id=STORE,
            item_id="item-a",
            msku="msku-a",
            owner_ref="A",
        )
    ]
    key = (DAY, ACCOUNT, STORE, "item-a", "msku-a")
    assert (
        load_daily_sales_log_summaries(pg_session, sales, access=alice)[key]["operation_log"]
        == "note-a"
    )
    assert load_daily_sales_log_summaries(pg_session, sales, access=bob)[key]["operation_log"] == ""


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("highlight", True),
        ("verify_status", "verified"),
        ("action_type", "bid_updated"),
        ("object_name", "another"),
        ("detected_at", datetime(2026, 10, 18)),
    ],
)
def test_event_reconciliation_catches_individual_field_corrections(
    pg_session: Session, field: str, new_value: object
) -> None:
    source = dict(
        id=9227099,
        event_date=DAY,
        store_id=STORE,
        item_id="item-a",
        msku="msku-a",
        action_type="bid_changed",
        object_name="keyword",
        log_content="original",
        highlight=False,
        verify_status="pending",
        updated_at=datetime(2026, 10, 17),
        detected_at=datetime(2026, 10, 17),
    )
    mapping = ({STORE: ACCOUNT}, {})
    assert _import_batch(pg_session, kind="system", rows=[source], mapping=mapping) == 1
    assert _import_batch(pg_session, kind="system", rows=[source], mapping=mapping) == 0
    changed = {**source, field: new_value}
    assert _import_batch(pg_session, kind="system", rows=[changed], mapping=mapping) == 1
    assert (
        pg_session.scalar(
            text(f"select {field} from ops_system_operation_events where legacy_id=9227099")
        )
        == new_value
    )
    assert _import_batch(pg_session, kind="system", rows=[changed], mapping=mapping) == 0
