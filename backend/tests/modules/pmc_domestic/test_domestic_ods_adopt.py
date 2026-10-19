"""PostgreSQL adoption: fresh create + re-run verify on existing domestic ODS tables."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import Settings, SettingsError, get_test_database_url
from app.db.domestic_ods_adopt import (
    DomesticOdsSchemaMismatchError,
    adopt_domestic_ods_tables,
)
from app.db.model_registry import register_productlist_sync_models

SQL_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "delivery" / "domestic-warehouse-ods-tables.sql"
)


@pytest.fixture
def isolated_postgresql_connection() -> Iterator:
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = get_test_database_url(settings)
    except (SettingsError, Exception):
        pytest.skip("isolated PostgreSQL test database is not configured")

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    register_productlist_sync_models()
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
    engine.dispose()


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


def test_hand_sql_then_adopt_matches_orm(isolated_postgresql_connection) -> None:
    isolated_postgresql_connection.execute(text(SQL_PATH.read_text(encoding="utf-8")))
    adopt_domestic_ods_tables(isolated_postgresql_connection)
