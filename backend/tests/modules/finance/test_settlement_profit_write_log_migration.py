"""Migration 0075 (settlement profit write log + permissions): offline + opt-in PostgreSQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.finance.settlement_profit import access
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic, _version

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261104_0075_fin_settle_write_log"
CALC_REVISION = "20261104_0074_fin_settle_calc"
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / f"{REVISION}.py"
EXPECTED_KEYS = {
    access.VIEW,
    *access.FINANCE_ACTIONS,
    access.FIELD_COST,
    access.FIELD_NET_PROFIT,
    access.FIELD_COMPANY_COST,
}


def _module():
    spec = importlib.util.spec_from_file_location("mig_0075", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_follows_calc_migration() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert script.get_revision(REVISION).down_revision == CALC_REVISION


def test_permission_rows_match_catalog_and_access_constants() -> None:
    rows = {p[0]: p for p in _module().PERMISSIONS}
    assert set(rows) == EXPECTED_KEYS
    catalog = {d.permission_key: d for d in PERMISSION_DEFINITIONS}
    for key, (_, name, kind, action_key, field_key, risk, _order) in rows.items():
        assert key in catalog, key
        assert catalog[key].permission_type == kind
        assert catalog[key].action_key == action_key
        assert catalog[key].field_key == field_key
        assert catalog[key].page_key == _module().PAGE_KEY
        assert catalog[key].risk_level == risk
        assert catalog[key].name == name


def _active_keys(engine: sa.Engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                sa.text(
                    "SELECT permission_key FROM app_permissions "
                    "WHERE is_active AND permission_key LIKE '%:finance:settlement-profit:%'"
                )
            ).scalars()
        )


def test_write_log_migration_postgresql_round_trip_and_blocked_rollback() -> None:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    database = create_database(url, "finsettlewritelog")
    engine = sa.create_engine(url.set(database=database), hide_parameters=True)
    try:
        assert _alembic(url, database, REVISION).returncode == 0
        assert _active_keys(engine) == EXPECTED_KEYS
        # empty log, no role grants: rollback deactivates (never deletes) the permissions
        down = _alembic(url, database, CALC_REVISION, command="downgrade")
        assert down.returncode == 0, down.stderr
        assert _version(url, database) == [CALC_REVISION]
        assert _active_keys(engine) == set()
        with engine.connect() as conn:
            kept = conn.execute(
                sa.text(
                    "SELECT count(*) FROM app_permissions "
                    "WHERE permission_key LIKE '%:finance:settlement-profit:%'"
                )
            ).scalar_one()
        assert kept == len(EXPECTED_KEYS)
        again = _alembic(url, database, REVISION)
        assert again.returncode == 0, again.stderr
        assert _active_keys(engine) == EXPECTED_KEYS

        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO manual_settlement_write_log (id, idempotency_key, actor_id, "
                    "actor_role, endpoint, request_hash, request_id, acted_at, response, "
                    "status_code) VALUES (gen_random_uuid(), 'k', '1', 'finance', 'POST /x', "
                    "'h', 'r', now(), '{}'::jsonb, 200)"
                )
            )
        blocked = _alembic(url, database, CALC_REVISION, command="downgrade")
        assert blocked.returncode != 0
        assert "0075 rollback blocked" in blocked.stderr
        assert _version(url, database) == [REVISION]
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT count(*) FROM manual_settlement_write_log")
            ).scalar_one()
        assert rows == 1
    finally:
        engine.dispose()
        drop_database(url, database)
