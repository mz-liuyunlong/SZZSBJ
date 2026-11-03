"""Migration 0072 (settlement profit V2): offline chain + opt-in PostgreSQL up/down."""

from __future__ import annotations

import ast
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.finance.settlement_profit_models import SETTLEMENT_PROFIT_TABLES
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic, _version

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261103_0072_fin_settle_profit_v2"
PREVIOUS = "20261102_0071_skill_lib"
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / f"{REVISION}.py"


def test_revision_is_single_head_after_skill_library() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == PREVIOUS


def test_migration_only_creates_and_drops_its_own_tables() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    created: list[str] = []
    dropped: list[str] = []
    other_ops: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "op"):
            continue
        name = node.func.attr
        if name == "create_table":
            created.append(ast.literal_eval(node.args[0]))
        elif name == "drop_table":
            dropped.append(ast.literal_eval(node.args[0]))
        elif name in {"create_index", "drop_index"}:
            table = ast.literal_eval(node.args[1]) if name == "create_index" else None
            if table is not None:
                assert table in SETTLEMENT_PROFIT_TABLES
        elif name != "f":  # op.f() only names a constraint
            other_ops.append(name)
    assert set(created) == set(SETTLEMENT_PROFIT_TABLES)
    assert sorted(created) == sorted(dropped)
    assert other_ops == []
    # the inventory-claim PRP owns the Lingxing WFS cost valuation ODS table
    assert "ods_lingxing_wfs_cost_valuation_flow" not in created
    assert "ods_lingxing_wfs_cost_valuation_lines" not in created


def test_postgresql_upgrade_downgrade_upgrade_on_disposable_database() -> None:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1 on the dedicated CI cluster
    database = create_database(url, "finsettle")
    try:
        previous = _alembic(url, database, PREVIOUS)
        assert previous.returncode == 0, previous.stderr
        up = _alembic(url, database, REVISION)
        assert up.returncode == 0, up.stderr
        assert _version(url, database) == [REVISION]
        engine = sa.create_engine(url.set(database=database), hide_parameters=True)
        try:
            with engine.connect() as conn:
                tables = set(sa.inspect(conn).get_table_names())
            assert set(SETTLEMENT_PROFIT_TABLES) <= tables
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO cfg_net_profit_allocation "
                        "(id, effective_month, updated_by, request_id, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), DATE '2026-10-01', 'fixture', 'req-fixture', "
                        "now(), now())"
                    )
                )
                row = conn.execute(
                    sa.text("SELECT fixed_cny, excluded_owner_ids FROM cfg_net_profit_allocation")
                ).one()
                assert str(row[0]) == "15000.0000"
                assert row[1] == []
            with engine.begin() as conn:
                bad = conn.begin_nested()
                try:
                    conn.execute(
                        sa.text(
                            "INSERT INTO cfg_net_profit_allocation "
                            "(id, effective_month, updated_by, request_id, created_at, updated_at)"
                            " VALUES (gen_random_uuid(), DATE '2026-11-02', 'f', 'r', now(), now())"
                        )
                    )
                    raise AssertionError("bill month not on day 1 must be rejected")
                except sa.exc.IntegrityError:
                    bad.rollback()
        finally:
            engine.dispose()
        down = _alembic(url, database, PREVIOUS, command="downgrade")
        assert down.returncode == 0, down.stderr
        assert _version(url, database) == [PREVIOUS]
        engine = sa.create_engine(url.set(database=database), hide_parameters=True)
        try:
            with engine.connect() as conn:
                tables = set(sa.inspect(conn).get_table_names())
            assert not (set(SETTLEMENT_PROFIT_TABLES) & tables)
        finally:
            engine.dispose()
        again = _alembic(url, database, "head")
        assert again.returncode == 0, again.stderr
        assert _version(url, database) == [REVISION]
    finally:
        drop_database(url, database)
