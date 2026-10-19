from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Index

import app.modules.data_pages.models  # noqa: F401
from alembic import command
from app.core.config import get_settings
from app.db.base import Base

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261020_0047_walmart_order_identity_guard"
PREVIOUS = "20261019_0046_operation_logs"


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _render_upgrade_sql() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
    return buffer.getvalue()


def _render_downgrade_sql() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.downgrade(config, f"{REVISION}:{PREVIOUS}", sql=True)
    return buffer.getvalue()


def test_order_identity_migration_is_additive_and_does_not_rewrite_history() -> None:
    sql = _render_upgrade_sql()
    assert "ADD COLUMN canonical_identity_hash VARCHAR(64)" in sql
    assert "ADD COLUMN is_identity_current BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ADD COLUMN provider_item_id VARCHAR(128)" in sql
    assert "ADD COLUMN item_id_resolution_source VARCHAR(64)" in sql
    assert "CREATE UNIQUE INDEX uq_fact_walmart_order_items_current_identity" in sql
    assert "WHERE is_identity_current = true" in sql
    assert "canonical_identity_hash ~ '^[0-9a-f]{64}$'" in sql
    assert "is_identity_current = false OR (canonical_identity_hash IS NOT NULL" in sql
    assert "nullif(btrim(store_id), '') IS NOT NULL" in sql
    assert "ck_fact_walmart_order_items_current_item_lineage" in sql
    assert "CREATE TABLE audit_walmart_order_item_conflicts" in sql
    assert "CONSTRAINT uq_audit_walmart_order_item_conflicts_transition" in sql
    assert "DELETE FROM fact_walmart_order_items" not in sql.upper()
    assert "UPDATE fact_walmart_order_items" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()


def test_order_identity_metadata_has_one_partial_current_index() -> None:
    table = Base.metadata.tables["fact_walmart_order_items"]
    indexes: dict[str, Index] = {
        str(index.name): index
        for index in table.indexes
        if isinstance(index, Index) and index.name is not None
    }
    current = indexes["uq_fact_walmart_order_items_current_identity"]
    assert current.unique is True
    assert [column.name for column in current.columns] == ["canonical_identity_hash"]
    assert str(current.dialect_options["postgresql"]["where"]) == "is_identity_current = true"


def test_order_identity_downgrade_removes_only_0047_objects() -> None:
    sql = _render_downgrade_sql()
    assert "0047 downgrade blocked: canonical identity or audit data exists" in sql
    assert "DROP TABLE audit_walmart_order_item_conflicts" in sql
    assert "DROP COLUMN is_identity_current" in sql
    assert "DROP COLUMN canonical_identity_hash" in sql
    assert "DROP COLUMN item_id_resolution_source" in sql
    assert "DROP COLUMN provider_item_id" in sql
    assert "DROP TABLE fact_walmart_order_items" not in sql


def test_conflict_audit_stores_hashes_and_field_names_not_payload_snapshots() -> None:
    columns = Base.metadata.tables["audit_walmart_order_item_conflicts"].c
    assert "prior_fact_id" in columns
    assert "canonical_fact_id" in columns
    assert columns["prior_fact_id"].nullable is False
    assert columns["canonical_fact_id"].nullable is False
    assert "prior_snapshot_hash" in columns
    assert "observed_snapshot_hash" in columns
    assert "differing_fields_json" in columns
    assert "prior_snapshot_json" not in columns
    assert "observed_snapshot_json" not in columns
    assert "payload_json" not in columns
