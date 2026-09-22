"""G3-A guardrails: the Gate 3 models, the Alembic revision and the registry agree.

Same approach as ``test_ods_models_migration``: render the revision offline against
PostgreSQL, parse the SQL back into table/column/index sets and compare with the ORM.
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
from app.modules.pmc_purchase import gate3_models
from app.modules.pmc_purchase.calculations import PurchaseThresholds

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20260922_0017"
PREVIOUS = "20260921_0013_business_rule_operation_logs"
EXPECTED_TABLES = {
    "dwd_purchase_plan",
    "dwd_purchase_order",
    "dwd_purchase_order_line_item",
    "dws_purchase_board",
    "dws_purchase_sku_cycle",
    "dws_purchase_pending",
    "manual_purchase_cycle_override",
    "rule_purchase_thresholds",
}
DWD_SOURCE_COLUMNS = {
    "id",
    "source_account_ref",
    "source_run_id",
    "source_ods_id",
    "source_observed_at",
    "provider_update_time",
    "builder_version",
    "created_at",
    "updated_at",
}
DWS_CALC_COLUMNS = {
    "id",
    "source_account_ref",
    "calc_version",
    "rule_version",
    "calculated_at",
    "source_lineage_json",
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
        tables[name] = {
            line.strip().split()[0]
            for line in body.splitlines()
            if line.strip()
            and not line.strip().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"))
        }
    return tables


def _parse_indexes(sql: str) -> set[str]:
    return set(re.findall(r"CREATE INDEX (\w+) ON", sql))


def test_metadata_declares_exactly_the_eight_gate3_tables() -> None:
    register_productlist_sync_models()
    assert set(gate3_models.PMC_PURCHASE_GATE3_TABLES) == EXPECTED_TABLES
    # Owner decision 2026-09-21 (#144): no ItemID override table.
    assert "manual_purchase_item_itemid_override" not in Base.metadata.tables
    for table in ("dwd_purchase_plan", "dwd_purchase_order", "dwd_purchase_order_line_item"):
        assert DWD_SOURCE_COLUMNS <= set(Base.metadata.tables[table].columns.keys()), table
    for table in ("dws_purchase_board", "dws_purchase_sku_cycle", "dws_purchase_pending"):
        assert DWS_CALC_COLUMNS <= set(Base.metadata.tables[table].columns.keys()), table


def test_migration_matches_orm_metadata() -> None:
    register_productlist_sync_models()
    sql = _render_upgrade_sql()
    created = _parse_create_tables(sql)
    assert set(created) == EXPECTED_TABLES
    for table in EXPECTED_TABLES:
        assert created[table] == set(Base.metadata.tables[table].columns.keys()), table
    orm_indexes = {
        index.name
        for table in EXPECTED_TABLES
        for index in Base.metadata.tables[table].indexes
        if index.name
    }
    assert _parse_indexes(sql) == orm_indexes
    upgrade_body = sql.split("-- Running upgrade")[-1]
    assert "DROP TABLE" not in upgrade_body.upper()
    assert "ALTER TABLE" not in upgrade_body.upper()


def test_migration_keys_and_seed_follow_convention() -> None:
    register_productlist_sync_models()
    sql = _render_upgrade_sql()
    for table in EXPECTED_TABLES:
        assert f"CONSTRAINT pk_{table} PRIMARY KEY (id)" in sql, table
    assert (
        sql.count(
            "FOREIGN KEY(source_run_id) REFERENCES gov_integration_sync_runs (id) "
            "ON DELETE RESTRICT"
        )
        == 3
    )
    uniques = {
        "uq_dwd_purchase_plan_sn": "(source_account_ref, plan_sn)",
        "uq_dwd_purchase_order_sn": "(source_account_ref, order_sn)",
        "uq_dwd_purchase_order_line_item_key": (
            "(source_account_ref, order_sn, order_item_id, plan_key)"
        ),
        "uq_dws_purchase_board_key": "(source_account_ref, order_sn, order_item_id, plan_key)",
        "uq_dws_purchase_sku_cycle_sku": "(source_account_ref, sku)",
        "uq_dws_purchase_pending_key": (
            "(source_account_ref, pending_type, order_sn, order_item_id, plan_key)"
        ),
        "uq_rule_purchase_thresholds_version": "(rule_key, version)",
    }
    for name, columns in uniques.items():
        assert f"CONSTRAINT {name} UNIQUE {columns}" in sql, name
    # Seed row = calculations defaults, one INSERT, nothing else written.
    defaults = PurchaseThresholds()
    inserts = [line for line in sql.splitlines() if line.startswith("INSERT INTO")]
    assert len(inserts) == 1 and inserts[0].startswith("INSERT INTO rule_purchase_thresholds")
    seed = inserts[0]
    for value in (
        defaults.s1_approval_days,
        defaults.s2_pending_days,
        defaults.default_cycle_days,
        defaults.auto_exclude_below_days,
        defaults.sample_window,
        defaults.min_samples_for_average,
        defaults.unstable_min_samples,
        defaults.unstable_range_days,
        defaults.baseline_evict_at_samples,
    ):
        assert f" {value}," in seed or f"({value}" in seed or f", {value}" in seed
    assert "'0.5000'" in seed and "'2026-08-01'" in seed
    body = sql.split("-- Running upgrade")[-1]
    # The only UPDATE is Alembic's own version bookkeeping.
    assert body.count("UPDATE ") == 1 and "UPDATE alembic_version" in body


def test_registry_and_alembic_env_register_the_models() -> None:
    env_source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "import app.modules.pmc_purchase.gate3_models" in env_source
    registry_source = (BACKEND_ROOT / "app" / "db" / "model_registry.py").read_text(
        encoding="utf-8"
    )
    assert "import app.modules.pmc_purchase.gate3_models" in registry_source
