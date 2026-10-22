"""PostgreSQL adoption: fresh create + re-run verify on existing domestic ODS tables."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.domestic_ods_adopt import (
    DomesticOdsSchemaMismatchError,
    adopt_domestic_ods_tables,
)
from app.db.model_registry import register_productlist_sync_models
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database

SQL_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "delivery" / "domestic-warehouse-ods-tables.sql"
)


@pytest.fixture
def isolated_postgresql_connection() -> Iterator:
    url = admin_url()
    database = create_database(url, "ods_contract")
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    engine = create_engine(url.set(database=database), poolclass=NullPool, hide_parameters=True)
    register_productlist_sync_models()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        create table if not exists gov_integration_sync_runs (id uuid primary key);
                        create table if not exists ods_api_raw_request_refs (id uuid primary key);
                        """
                    )
                )
                yield connection
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()
        drop_database(url, database)


def test_adopt_creates_then_revalidates_without_error(isolated_postgresql_connection) -> None:
    adopt_domestic_ods_tables(isolated_postgresql_connection)
    adopt_domestic_ods_tables(isolated_postgresql_connection)


def test_adopt_rejects_column_drift(isolated_postgresql_connection) -> None:
    ddl = SQL_PATH.read_text(encoding="utf-8")
    isolated_postgresql_connection.execute(text(ddl))
    isolated_postgresql_connection.execute(
        text("alter table ods_lingxing_domestic_warehouses add column drift_probe integer")
    )
    with pytest.raises(DomesticOdsSchemaMismatchError, match="column set mismatch"):
        adopt_domestic_ods_tables(isolated_postgresql_connection)


def test_adopt_rejects_timestamp_without_time_zone(isolated_postgresql_connection) -> None:
    adopt_domestic_ods_tables(isolated_postgresql_connection)
    isolated_postgresql_connection.execute(
        text(
            """
            alter table ods_lingxing_domestic_warehouses
            alter column observed_at type timestamp without time zone
            """
        )
    )
    with pytest.raises(DomesticOdsSchemaMismatchError, match="observed_at"):
        adopt_domestic_ods_tables(isolated_postgresql_connection)


def test_adopt_rejects_varchar_without_length(isolated_postgresql_connection) -> None:
    adopt_domestic_ods_tables(isolated_postgresql_connection)
    isolated_postgresql_connection.execute(
        text(
            """
            alter table ods_lingxing_domestic_warehouses
            alter column source_account_ref type varchar
            """
        )
    )
    with pytest.raises(DomesticOdsSchemaMismatchError, match="source_account_ref"):
        adopt_domestic_ods_tables(isolated_postgresql_connection)


def test_hand_sql_then_adopt_matches_orm(isolated_postgresql_connection) -> None:
    isolated_postgresql_connection.execute(text(SQL_PATH.read_text(encoding="utf-8")))
    adopt_domestic_ods_tables(isolated_postgresql_connection)


@pytest.mark.parametrize(
    "kind",
    [
        "primary",
        "foreign",
        "unique",
        "check",
        "not_valid",
        "nullable",
        "index_order",
        "missing_index",
    ],
)
def test_adopt_refuses_constraint_and_index_drift(isolated_postgresql_connection, kind):
    conn = isolated_postgresql_connection
    adopt_domestic_ods_tables(conn)
    table = "ods_lingxing_domestic_warehouses"
    if kind in {"primary", "foreign", "unique", "check", "not_valid"}:
        types = {"primary": "p", "foreign": "f", "unique": "u", "check": "c", "not_valid": "f"}
        name, definition = conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid=CAST(:table AS regclass) AND contype=:kind LIMIT 1"
            ),
            {"table": table, "kind": types[kind]},
        ).one()
        quoted = conn.dialect.identifier_preparer.quote(name)
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {quoted}"))
        if kind == "not_valid":
            conn.execute(
                text(f"ALTER TABLE {table} ADD CONSTRAINT {quoted} {definition} NOT VALID")
            )
    elif kind == "nullable":
        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN observed_at DROP NOT NULL"))
    else:
        conn.execute(text("DROP INDEX ix_ods_domestic_inventory_wh_sku"))
        if kind == "index_order":
            conn.execute(
                text(
                    "CREATE INDEX ix_ods_domestic_inventory_wh_sku ON "
                    "ods_lingxing_domestic_inventory (sku,source_warehouse_id,source_account_ref)"
                )
            )
    with pytest.raises(DomesticOdsSchemaMismatchError):
        adopt_domestic_ods_tables(conn)


def test_partial_ods_set_is_refused_without_creating_empty_replacements(
    isolated_postgresql_connection,
):
    conn = isolated_postgresql_connection
    adopt_domestic_ods_tables(conn)
    conn.execute(text("DROP TABLE ods_lingxing_domestic_inventory_events"))
    with pytest.raises(DomesticOdsSchemaMismatchError, match="partial table set"):
        adopt_domestic_ods_tables(conn)
    assert (
        conn.scalar(text("SELECT to_regclass('public.ods_lingxing_domestic_inventory_events')"))
        is None
    )
