"""Exercise 0100 rollback against a disposable, explicitly opted-in CI database."""

import runpy
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database

ROOT = Path(__file__).resolve().parents[3]
REV = "20261127_0100_sku_ad_progress_foundation"


def test_0100_rejects_nonempty_rollback_and_allows_empty_rollback():
    url = admin_url()
    database = create_database(url, "sku_0100")
    engine = sa.create_engine(url.set(database=database))
    try:
        migration = runpy.run_path(str(ROOT / f"alembic/versions/{REV}.py"))
        names = set(migration["DOWNGRADE_TABLES"])
        assert len(names) == 16
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            migration["upgrade"]()
            connection.execute(
                sa.text(
                    "INSERT INTO mart_new_product_sku_progress_current "
                    "(source_account_ref, sku_identity_id, sku, identity_verified, "
                    "listings_json, eligible) "
                    "VALUES ('synthetic', :id, 'SKU-TEST', true, '[]'::jsonb, true)"
                ),
                {"id": uuid4()},
            )
        with (
            pytest.raises(sa.exc.DBAPIError, match="0100 rollback blocked"),
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            migration["downgrade"]()
        with engine.begin() as connection:
            assert names <= set(sa.inspect(connection).get_table_names())
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM mart_new_product_sku_progress_current")
                )
                == 1
            )
            connection.execute(sa.text("DELETE FROM mart_new_product_sku_progress_current"))
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            migration["downgrade"]()
            assert names.isdisjoint(sa.inspect(connection).get_table_names())
    finally:
        engine.dispose()
        drop_database(url, database)
