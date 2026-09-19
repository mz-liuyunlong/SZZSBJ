"""PR-B guardrails: the purchase ODS models, the Alembic revision and the registry agree.

No database is used. The revision is rendered through Alembic's offline (``--sql``)
mode against the PostgreSQL dialect and parsed back into table/column/index sets, then
compared with the ORM metadata. This catches the drift ``alembic check`` would report
in production without needing a live ``DATABASE_URL`` in CI.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_purchase import models as pmc_models

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20260919_0016"
PREVIOUS = "20260918_0015"
EXPECTED_TABLES = {
    "ods_lingxing_purchase_plans",
    "ods_lingxing_purchase_orders",
    "ods_lingxing_purchase_order_items",
    "ods_lingxing_receipt_orders",
    "ods_lingxing_receipt_order_items",
}
GOVERNANCE_COLUMNS = {
    "id",
    "run_id",
    "raw_request_ref_id",
    "source_account_ref",
    "source_item_ordinal",
    "payload_json",
    "observed_at",
    "created_at",
}


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


def _render_upgrade_sql() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
    return buffer.getvalue()


def _parse_create_tables(sql: str) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for match in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
        name, body = match.group(1), match.group(2)
        columns = {
            line.strip().split()[0]
            for line in body.splitlines()
            if line.strip()
            and not line.strip().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"))
        }
        tables[name] = columns
    return tables


def _parse_indexes(sql: str) -> set[str]:
    return set(re.findall(r"CREATE INDEX (\w+) ON", sql))


def test_metadata_declares_exactly_the_five_ods_tables() -> None:
    assert set(pmc_models.PMC_PURCHASE_ODS_TABLES) == EXPECTED_TABLES
    for table in EXPECTED_TABLES:
        assert table in Base.metadata.tables, table
        columns = set(Base.metadata.tables[table].columns.keys())
        assert GOVERNANCE_COLUMNS <= columns, table
        assert Base.metadata.tables[table].columns["payload_json"].nullable is False


def test_migration_matches_orm_metadata() -> None:
    sql = _render_upgrade_sql()
    created = _parse_create_tables(sql)
    assert set(created) == EXPECTED_TABLES

    for table in EXPECTED_TABLES:
        orm_columns = set(Base.metadata.tables[table].columns.keys())
        assert created[table] == orm_columns, table

    orm_indexes = {
        index.name
        for table in EXPECTED_TABLES
        for index in Base.metadata.tables[table].indexes
        if index.name
    }
    assert _parse_indexes(sql) == orm_indexes
    # Append-only ODS: the upgrade only creates; it never drops or rewrites existing tables.
    upgrade_body = sql.split("-- Running upgrade")[-1]
    assert "DROP TABLE" not in upgrade_body.upper()
    assert "ALTER TABLE" not in upgrade_body.upper()


def test_migration_constraints_and_keys_follow_ods_convention() -> None:
    sql = _render_upgrade_sql()
    for table in EXPECTED_TABLES:
        assert f"CONSTRAINT pk_{table} PRIMARY KEY (id)" in sql
        assert f"CONSTRAINT ck_{table}_source_item_ordinal CHECK (source_item_ordinal >= 0)" in sql
        assert (
            "FOREIGN KEY(run_id) REFERENCES gov_integration_sync_runs (id) ON DELETE RESTRICT"
            in sql
        )
    header_uniques = {
        "uq_ods_purchase_plan_run_sn": "(run_id, source_account_ref, plan_sn)",
        "uq_ods_purchase_order_run_sn": "(run_id, source_account_ref, order_sn)",
        "uq_ods_receipt_order_run_sn": "(run_id, source_account_ref, order_sn)",
        "uq_ods_purchase_order_item_run_key": "(run_id, source_account_ref, order_sn, item_id)",
        "uq_ods_receipt_order_item_run_line": (
            "(run_id, source_account_ref, receipt_order_sn, line_ordinal)"
        ),
    }
    for name, columns in header_uniques.items():
        assert f"CONSTRAINT {name} UNIQUE {columns}" in sql, name
    assert sql.count("payload_json JSONB NOT NULL") == len(EXPECTED_TABLES)


def test_registry_and_alembic_env_register_the_models() -> None:
    register_productlist_sync_models()
    assert "ods_lingxing_purchase_plans" in Base.metadata.tables
    env_source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "import app.modules.pmc_purchase.models" in env_source
    registry_source = (BACKEND_ROOT / "app" / "db" / "model_registry.py").read_text(
        encoding="utf-8"
    )
    assert "import app.modules.pmc_purchase.models" in registry_source
