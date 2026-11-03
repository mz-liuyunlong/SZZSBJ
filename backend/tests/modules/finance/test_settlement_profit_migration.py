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


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))


def test_revision_follows_skill_library_and_is_an_ancestor_of_head() -> None:
    script = _script()
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    (head,) = script.get_heads()
    assert REVISION in {rev.revision for rev in script.walk_revisions(PREVIOUS, head)}


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
        assert _version(url, database) == _script().get_heads()
    finally:
        drop_database(url, database)


CALC_REVISION = "20261104_0074_fin_settle_calc"
CALC_MIGRATION = BACKEND_ROOT / "alembic" / "versions" / f"{CALC_REVISION}.py"


def test_calc_migration_only_alters_settlement_profit_tables() -> None:
    assert _script().get_revision(CALC_REVISION).down_revision == REVISION
    tree = ast.parse(CALC_MIGRATION.read_text(encoding="utf-8"))
    consts = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    touched: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "op"):
            continue
        assert node.func.attr not in {"create_table", "drop_table"}
        if node.func.attr in {"add_column", "drop_column", "alter_column"}:
            touched.add(consts[node.args[0].id])
        elif node.func.attr in {"drop_constraint"}:
            touched.add(consts[node.args[1].id])
        elif node.func.attr == "create_check_constraint":
            touched.add(consts[node.args[1].id])
    assert touched <= set(SETTLEMENT_PROFIT_TABLES)
    # rollback never deletes or truncates: no raw SQL is executed by the migration
    raw_sql = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == "execute"
    ]
    assert raw_sql == []


def test_calc_migration_postgresql_round_trip_and_blocked_rollback() -> None:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    empty = create_database(url, "finsettlecalcempty")
    try:
        # empty tables: schema rollback and re-upgrade work
        assert _alembic(url, empty, CALC_REVISION).returncode == 0
        down = _alembic(url, empty, REVISION, command="downgrade")
        assert down.returncode == 0, down.stderr
        assert _version(url, empty) == [REVISION]
        again = _alembic(url, empty, "head")
        assert again.returncode == 0, again.stderr
    finally:
        drop_database(url, empty)

    database = create_database(url, "finsettlecalcmig")
    try:
        assert _alembic(url, database, CALC_REVISION).returncode == 0
        engine = sa.create_engine(url.set(database=database), hide_parameters=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO fact_settlement_unassigned_amounts (id, line_key, store_id, "
                        "bill_month, source_kind, source_ref, amount_cny, status, "
                        "assigned_store_id, calc_version, created_at, updated_at) VALUES "
                        "(gen_random_uuid(), 'k', '__unmapped__', DATE '2030-01-01', "
                        "'inventory_unmapped_store', 'h', 70, 'assigned', 'store-a', 1, "
                        "now(), now())"
                    )
                )
            with engine.begin() as conn:
                bad = conn.begin_nested()
                try:
                    conn.execute(
                        sa.text(
                            "INSERT INTO fact_settlement_unassigned_amounts (id, line_key, "
                            "store_id, bill_month, source_kind, source_ref, calc_version, "
                            "created_at, updated_at) VALUES (gen_random_uuid(), 'k2', 's', "
                            "DATE '2030-01-01', 'x', 'y', 1, now(), now())"
                        )
                    )
                    raise AssertionError("a 待指定 row without any amount must be rejected")
                except sa.exc.IntegrityError:
                    bad.rollback()
            # with a record present the rollback is refused and nothing is deleted
            blocked = _alembic(url, database, REVISION, command="downgrade")
            assert blocked.returncode != 0
            assert "0074 rollback blocked" in blocked.stderr
            assert _version(url, database) == [CALC_REVISION]
            with engine.connect() as conn:
                kept = conn.execute(
                    sa.text("SELECT count(*) FROM fact_settlement_unassigned_amounts")
                ).scalar_one()
            assert kept == 1
        finally:
            engine.dispose()
    finally:
        drop_database(url, database)


INVENTORY_CLAIM_REVISION = "20261103_0073_wfs_cost_valuation_flow"


def test_alembic_graph_single_linear_head() -> None:
    """PRP §10: whichever of #308 (0073) / #309 (0074) merges later re-points onto the other.

    After both are on main there must be one head, both revisions on its chain, and no fork
    under 0072 (two migrations with the same parent).
    """
    script = _script()
    heads = script.get_heads()
    assert len(heads) == 1, f"multiple alembic heads: {heads}"
    chain = {rev.revision for rev in script.walk_revisions("base", heads[0])}
    present = {rev.revision for rev in script.walk_revisions()}
    for revision in (INVENTORY_CLAIM_REVISION, CALC_REVISION):
        if revision in present:
            assert revision in chain
    children = [
        rev.revision
        for rev in script.walk_revisions()
        if rev.down_revision == REVISION
        or (isinstance(rev.down_revision, tuple) and REVISION in rev.down_revision)
    ]
    assert len(children) == 1, f"fork under {REVISION}: {children}"
