"""创建默认值按店铺（migration 0079）。PostgreSQL opt-in only."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from tests.modules.pmc_wfs.schema_support import integration_target, run_migration

MIGRATION = "20261104_0079_wfs_store_creation_defaults.py"
TABLE = "ref_wfs_store_creation_defaults"


def test_migration_0079_matches_orm_and_downgrade_keeps_saved_rows():
    if os.environ.get("WFS_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required (WFS_LOCAL_INTEGRATION=1)")
    from tests.modules.pmc_wfs.schema_support import table_structure

    register_productlist_sync_models()
    url, database = integration_target()
    token = uuid4().hex[:12]
    mig, orm = f"wfs_mig0079_{token}", f"wfs_orm0079_{token}"
    admin = create_engine(url, hide_parameters=True)
    try:
        with admin.begin() as c:
            assert c.scalar(text("select current_database()")) == database
            for schema in (mig, orm):
                c.execute(text(f'CREATE SCHEMA "{schema}"'))
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            run_migration(c, MIGRATION)
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{orm}"'))
            Base.metadata.create_all(c, tables=[Base.metadata.tables[TABLE]])
        with admin.connect() as c:
            assert table_structure(c, mig, (TABLE,)) == table_structure(c, orm, (TABLE,))
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(
                text(
                    f"INSERT INTO {TABLE} (source_account_ref, store_id, transport,"
                    " ship_date_offset, pallet_boxes, mixed_boxes, carrier_opt, its,"
                    " updated_by, updated_at) VALUES ('a', 's', 'LTL', 15, 16, 0, 'own',"
                    " false, 't', now())"
                )
            )
        with pytest.raises(RuntimeError, match="refusing to drop"):
            with admin.begin() as c:
                c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
                run_migration(c, MIGRATION, "downgrade")
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(text(f"DELETE FROM {TABLE}"))
            run_migration(c, MIGRATION, "downgrade")
        with admin.connect() as c:
            left = c.scalar(
                text("select count(*) from information_schema.tables where table_schema = :s"),
                {"s": mig},
            )
            assert left == 0
    finally:
        with admin.begin() as c:
            for schema in (mig, orm):
                assert schema.startswith("wfs_") and token in schema
                c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
