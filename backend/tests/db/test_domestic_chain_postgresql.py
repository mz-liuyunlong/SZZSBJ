"""Real PostgreSQL checks for the domestic chain through revision 0054.

The extra-allocation table is created by the existing merge revision. These tests
use disposable databases and synthetic rows only.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from tests.db.domestic_postgresql_support import (
    admin_url as _admin_url,
)
from tests.db.domestic_postgresql_support import (
    connect as _connect,
)
from tests.db.domestic_postgresql_support import (
    create_database,
)
from tests.db.domestic_postgresql_support import (
    drop_database as _drop,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD = "20261022_0054_merge_walmart_identity_and_domestic_packing"
DOMESTIC_0049 = "20261020_0049_domestic_inbound_board"
DOMESTIC_TABLES = (
    "dwd_domestic_receipt_batch",
    "dwd_domestic_receipt_batch_link",
    "evt_domestic_packing_events",
    "gov_domestic_board_publications",
    "mart_domestic_inbound_batch_board",
    "ods_lingxing_domestic_batches",
    "ods_lingxing_domestic_inventory",
    "ods_lingxing_domestic_inventory_events",
    "ods_lingxing_domestic_warehouse_statements",
    "ods_lingxing_domestic_warehouses",
    "ops_domestic_packing_allocations",
    "ops_domestic_packing_box_lines",
    "ops_domestic_packing_box_sets",
    "ops_domestic_packing_extra_allocations",
    "ops_domestic_packing_manual_requests",
    "ops_domestic_packing_notes",
    "ops_domestic_packing_notification_outbox",
    "ops_domestic_packing_orders",
    "ops_domestic_packing_variance_cases",
    "ops_domestic_pk_sequences",
)


def _alembic(
    url: URL, database: str, revision: str, command: str = "upgrade"
) -> subprocess.CompletedProcess[str]:
    target = url.set(database=database)
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["TEST_DATABASE_URL"] = target.render_as_string(hide_password=False)
    env["PYTHONUTF8"] = "1"
    env.pop("PRODUCTION_MIGRATIONS_AUTHORIZED", None)
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "alembic", command, revision],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _version(url: URL, database: str) -> list[str]:
    with _connect(url, database) as conn:
        rows = conn.execute("SELECT version_num FROM alembic_version ORDER BY 1")
        return [row[0] for row in rows]


def _tables(url: URL, database: str) -> set[str]:
    with _connect(url, database) as conn:
        rows = conn.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(DOMESTIC_TABLES),),
        )
        return {row[0] for row in rows}


def test_fresh_database_reaches_0054_with_all_domestic_tables() -> None:
    url = _admin_url()
    database = create_database(url, "empty")
    try:
        first = _alembic(url, database, "head")
        assert first.returncode == 0, first.stderr
        assert _version(url, database) == [HEAD]
        assert _tables(url, database) == set(DOMESTIC_TABLES)
        _assert_orm_tables(url, database)
        with _connect(url, database) as conn:
            formatted = conn.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'ops_domestic_packing_extra_allocations'
                  AND a.attname = 'created_at'
                """
            ).fetchone()
            assert formatted is not None
            assert formatted[0] == "timestamp with time zone"
        second = _alembic(url, database, "head")
        assert second.returncode == 0, second.stderr
        assert "Running upgrade" not in second.stdout + second.stderr
        assert _version(url, database) == [HEAD]
        _seed_0049(url, database)
        order_id = _seed_order(url, database)
        _exercise_stock(url, database, order_id, warehouse_read=False)
        _exercise_stock(url, database, order_id, warehouse_read=True)
    finally:
        _drop(url, database)


def test_database_at_0049_keeps_synthetic_rows_when_upgraded_to_0054() -> None:
    url = _admin_url()
    database = create_database(url, "from_0049")
    try:
        stopped = _alembic(url, database, DOMESTIC_0049)
        assert stopped.returncode == 0, stopped.stderr
        assert _version(url, database) == [DOMESTIC_0049]
        marker = _seed_0049(url, database)
        before = _snapshot_0049(url, database)
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        log = upgraded.stdout + upgraded.stderr
        upgrade_lines = [line for line in log.splitlines() if "Running upgrade" in line]
        assert len(upgrade_lines) == 6, log
        for revision in (
            "20261020_0047_walmart_order_identity_guard",
            "20261020_0050_domestic_packing_approval",
            "20261021_0051_domestic_packing_lifecycle",
            "20261021_0052_domestic_packing_manual",
            "20261022_0053_domestic_packing_production_compat",
            HEAD,
        ):
            assert any(revision in line.split(" -> ")[-1] for line in upgrade_lines), log
        assert not any(
            " -> 20261019_0047_domestic" in line
            or " -> 20261019_0048_domestic" in line
            or " -> " + DOMESTIC_0049 in line
            for line in upgrade_lines
        )
        assert _version(url, database) == [HEAD]
        assert _snapshot_0049(url, database) == before
        assert _marker_unchanged(url, database, marker)
        with _connect(url, database) as conn:
            identity = conn.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'fact_walmart_order_items'
                  AND column_name = 'is_identity_current'
                """
            ).fetchone()
            assert identity is not None and identity[0] == 1
            assert (
                conn.execute(
                    "SELECT to_regclass('public.ops_domestic_packing_extra_allocations')"
                ).fetchone()[0]
                == "ops_domestic_packing_extra_allocations"
            )
        repeated = _alembic(url, database, "head")
        assert repeated.returncode == 0, repeated.stderr
        assert "Running upgrade" not in repeated.stdout + repeated.stderr
        assert _snapshot_0049(url, database) == before
        _assert_orm_tables(url, database)
        order_id = _seed_order(url, database)
        _exercise_stock(url, database, order_id, warehouse_read=False)
        _exercise_stock(url, database, order_id, warehouse_read=True)
    finally:
        _drop(url, database)


def _migration(revision):
    path = next((BACKEND_ROOT / "alembic" / "versions").glob(f"*{revision}*.py"))
    spec = importlib.util.spec_from_file_location("frozen_domestic_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_existing(url, database, revision):
    engine = sa.create_engine(url.set(database=database), hide_parameters=True)
    try:
        with engine.begin() as conn:
            module = _migration(revision)
            module.op = Operations(MigrationContext.configure(conn))
            if revision == "0053":
                module._create_warehouse_tables()
            else:
                module.op.create_table(module.TABLE, *module._elements())
                module.op.create_index(
                    module.INDEX,
                    module.TABLE,
                    ["source_account_ref", "warehouse_id", "source_board_id"],
                )
    finally:
        engine.dispose()


def _drift(conn, table, kind):
    if kind in {"unique", "check", "foreign", "not_valid", "deferred", "cascade", "wrong_schema"}:
        code = {"unique": "u", "check": "c"}.get(kind, "f")
        name, definition = conn.execute(
            "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid=%s::regclass AND contype=%s "
            + (
                "AND confrelid='public.ops_domestic_packing_orders'::regclass "
                if kind == "wrong_schema"
                else ""
            )
            + "ORDER BY conname LIMIT 1",
            (table, code),
        ).fetchone()
        from psycopg import sql

        conn.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(table), sql.Identifier(name)
            )
        )
        if kind in {"not_valid", "deferred", "cascade", "wrong_schema"}:
            if kind == "not_valid":
                definition += " NOT VALID"
            elif kind == "deferred":
                definition += " DEFERRABLE INITIALLY DEFERRED"
            elif kind == "cascade":
                definition = definition.replace("ON DELETE RESTRICT", "ON DELETE CASCADE")
            else:
                conn.execute("CREATE SCHEMA synthetic_other")
                conn.execute(
                    "CREATE TABLE synthetic_other.ops_domestic_packing_orders (id uuid PRIMARY KEY)"
                )
                conn.execute(
                    "INSERT INTO synthetic_other.ops_domestic_packing_orders "
                    "SELECT id FROM public.ops_domestic_packing_orders"
                )
                definition, replaced = re.subn(
                    r"REFERENCES (?:public\.)?ops_domestic_packing_orders",
                    "REFERENCES synthetic_other.ops_domestic_packing_orders",
                    definition,
                )
                assert replaced == 1, definition
            conn.execute(
                sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} ").format(
                    sql.Identifier(table), sql.Identifier(name)
                )
                + sql.SQL(definition)
            )
    elif kind == "default":
        conn.execute(f"ALTER TABLE {table} ALTER COLUMN qty SET DEFAULT 1")
    elif kind == "nullable":
        conn.execute(f"ALTER TABLE {table} ALTER COLUMN created_at DROP NOT NULL")
    elif kind == "timestamp":
        conn.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at TYPE timestamp without time zone"
        )
    elif kind == "column":
        conn.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_drift integer")
    else:
        conn.execute("DROP INDEX ix_packing_extra_source")
        if kind == "index_order":
            conn.execute(
                f"CREATE INDEX ix_packing_extra_source ON {table} "
                "(sku,warehouse_id,source_board_id)"
            )
        elif kind == "invalid_index":
            # Reproduce a genuinely invalid index left by a failed concurrent build.
            with pytest.raises(psycopg.errors.DivisionByZero):
                conn.execute(
                    f"CREATE INDEX CONCURRENTLY ix_packing_extra_source ON {table} "
                    "((qty / (qty - qty)))"
                )


@pytest.mark.parametrize("drift", [None, "column", "unique", "check", "foreign", "not_valid"])
def test_existing_warehouse_tables_must_match_0053_before_upgrade(drift):
    url = _admin_url()
    database = create_database(url, "warehouse_shape")
    revision_0052 = "20261021_0052_domestic_packing_manual"
    try:
        created = _alembic(url, database, revision_0052)
        assert created.returncode == 0, created.stderr
        # Create pre-existing tables using frozen DDL, never rewrite alembic_version.
        _prepare_existing(url, database, "0053")
        if drift:
            with _connect(url, database) as conn:
                _drift(conn, "ops_domestic_packing_notification_outbox", drift)
        before = _constraint_snapshot(url, database)
        result = _alembic(url, database, "20261022_0053_domestic_packing_production_compat")
        if drift:
            assert result.returncode != 0
            assert "PACKING_WAREHOUSE_TABLE_SHAPE_MISMATCH" in result.stderr
            assert _version(url, database) == [revision_0052]
            assert _constraint_snapshot(url, database) == before
        else:
            assert result.returncode == 0, result.stderr
    finally:
        _drop(url, database)


def _constraint_snapshot(url, database):
    with _connect(url, database) as conn:
        return conn.execute(
            "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE connamespace='public'::regnamespace "
            "ORDER BY 1,2"
        ).fetchall()


def test_mismatched_extra_allocation_table_rejects_0054() -> None:
    url = _admin_url()
    database = create_database(url, "mismatch")
    try:
        prepared = _alembic(url, database, "20261022_0053_domestic_packing_production_compat")
        assert prepared.returncode == 0, prepared.stderr
        with _connect(url, database) as conn:
            conn.execute(
                "CREATE TABLE ops_domestic_packing_extra_allocations (id uuid PRIMARY KEY)"
            )
        rejected = _alembic(url, database, "head")
        assert rejected.returncode != 0
        assert "PACKING_EXTRA_ALLOCATIONS" in rejected.stderr
        assert "COLUMNS_MISMATCH" in rejected.stderr
        assert _version(url, database) == ["20261022_0053_domestic_packing_production_compat"]
    finally:
        _drop(url, database)


def _snapshot_0049(url, database):
    names = [name for name in DOMESTIC_TABLES if name.startswith(("ods_", "dwd_", "gov_", "mart_"))]
    with _connect(url, database) as conn:
        return {
            name: conn.execute(f"SELECT to_jsonb(t)::text FROM {name} t ORDER BY 1").fetchall()
            for name in names
        }


def _marker_unchanged(url: URL, database: str, publication_id: str) -> bool:
    with _connect(url, database) as conn:
        row = conn.execute(
            """
            SELECT is_current, builder_version
            FROM gov_domestic_board_publications
            WHERE id = %s
            """,
            (publication_id,),
        ).fetchone()
    return row == (True, "synthetic-0049")


def _seed_0049(url: URL, database: str) -> str:
    now = "2026-10-20T00:00:00+00"
    publication_id = str(uuid4())
    board_id = str(uuid4())
    run_id = str(uuid4())
    interface_id = str(uuid4())
    policy_id = str(uuid4())
    work_id = str(uuid4())
    blob_id = str(uuid4())
    ref_id = str(uuid4())
    receipt_id = str(uuid4())
    with _connect(url, database) as conn:
        conn.execute(
            """
            INSERT INTO gov_integration_interfaces (
                id, provider, interface_key, display_name, method, endpoint_path,
                request_kind, handler_key, contract_version, outbound_enabled,
                created_at, updated_at
            ) VALUES (
                %s, 'lingxing', 'synthetic-domestic', 'Synthetic', 'POST', '/synthetic',
                'offset_page', 'synthetic', 'v1', false, %s, %s
            )
            """,
            (interface_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO gov_raw_retention_policies (
                id, policy_key, hot_retention_days, archive_required, legal_hold,
                is_active, created_at, updated_at
            ) VALUES (%s, 'synthetic-policy', 1, false, false, true, %s, %s)
            """,
            (policy_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO gov_integration_sync_runs (
                id, interface_id, provider, interface_key, source_account_ref,
                trigger_type, status, idempotency_key, queued_at,
                work_items_total, work_items_succeeded, work_items_failed,
                records_seen, records_written, created_at
            ) VALUES (
                %s, %s, 'lingxing', 'synthetic-domestic', 'synthetic-account',
                'manual', 'succeeded', 'synthetic-run', %s,
                0, 0, 0, 0, 0, %s
            )
            """,
            (run_id, interface_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO gov_integration_sync_run_work_items (
                id, run_id, ordinal, request_kind, status, attempt_count,
                offset_value, length_value, request_safe_params, created_at
            ) VALUES (
                %s, %s, 1, 'offset_page', 'succeeded', 0, 0, 1, '{}'::jsonb, %s
            )
            """,
            (work_id, run_id, now),
        )
        conn.execute(
            """
            INSERT INTO ods_api_raw_blobs (
                id, response_hash, payload_json, payload_bytes, content_type,
                storage_mode, retention_policy_id, received_at, created_at
            ) VALUES (
                %s, %s, '{}'::jsonb, 2, 'application/json',
                'database', %s, %s, %s
            )
            """,
            (blob_id, "a" * 64, policy_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO ods_api_raw_request_refs (
                id, run_id, work_item_id, raw_blob_id, request_kind, attempt_no,
                request_safe_params, is_success, requested_at, received_at, created_at
            ) VALUES (
                %s, %s, %s, %s, 'offset_page', 1, '{}'::jsonb, true, %s, %s, %s
            )
            """,
            (ref_id, run_id, work_id, blob_id, now, now, now),
        )
        conn.execute(
            """
            INSERT INTO ods_lingxing_domestic_warehouses (
                id, run_id, raw_request_ref_id, source_account_ref, source_item_ordinal,
                payload_json, observed_at, created_at, source_warehouse_id, warehouse_name
            ) VALUES (
                %s, %s, %s, 'synthetic-account', 0, '{}'::jsonb, %s, %s, '16168',
                'Synthetic Warehouse'
            )
            """,
            (str(uuid4()), run_id, ref_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO dwd_domestic_receipt_batch (
                id, source_account_ref, source_run_id, source_ods_id, source_observed_at,
                builder_version, created_at, updated_at, receipt_order_sn, line_ordinal
            ) VALUES (
                %s, 'synthetic-account', %s, %s, %s, 'synthetic-0049', %s, %s, 'R-1', 0
            )
            """,
            (receipt_id, run_id, str(uuid4()), now, now, now),
        )
        conn.execute(
            """
            INSERT INTO dwd_domestic_receipt_batch_link (
                id, source_account_ref, receipt_batch_id, mapping_status,
                created_at, updated_at
            ) VALUES (%s, 'synthetic-account', %s, 'unresolved', %s, %s)
            """,
            (str(uuid4()), receipt_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO gov_domestic_board_publications (
                id, source_account_ref, source_warehouse_id, status, is_current,
                batch_run_id, statement_run_ids, coverage_start, coverage_end,
                source_observed_at, published_at, builder_version, quality_report
            ) VALUES (
                %s, 'synthetic-account', '16168', 'published', true,
                %s, '[]'::jsonb, '2026-10-01', '2026-10-02', %s, %s, 'synthetic-0049',
                '{}'::jsonb
            )
            """,
            (publication_id, run_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO mart_domestic_inbound_batch_board (
                publication_id, id, source_account_ref, source_warehouse_id,
                inbound_order_sn, sku, attribution_key, payload_json
            ) VALUES (
                %s, %s, 'synthetic-account', '16168', 'IB-SYNTH', 'SKU-SYNTH',
                'synthetic', '{}'::jsonb
            )
            """,
            (publication_id, board_id),
        )
    return publication_id


@pytest.mark.parametrize(
    "drift",
    [
        None,
        "nullable",
        "default",
        "timestamp",
        "unique",
        "check",
        "foreign",
        "not_valid",
        "deferred",
        "cascade",
        "wrong_schema",
        "index_order",
        "missing_index",
        "invalid_index",
    ],
)
def test_existing_extra_table_is_adopted_only_if_complete(drift):
    url = _admin_url()
    database = create_database(url, "extra_contract")
    revision = "20261022_0053_domestic_packing_production_compat"
    try:
        prepared = _alembic(url, database, revision)
        assert prepared.returncode == 0, prepared.stderr
        _seed_0049(url, database)
        _prepare_existing(url, database, "0054")
        order_id = _seed_order(url, database)
        _exercise_stock(url, database, order_id, warehouse_read=False)
        with _connect(url, database) as conn:
            if drift:
                _drift(conn, "ops_domestic_packing_extra_allocations", drift)
            before = conn.execute(
                "SELECT to_jsonb(t)::text FROM ops_domestic_packing_extra_allocations t"
            ).fetchall()
        result = _alembic(url, database, "head")
        if drift:
            assert result.returncode != 0
            assert "PACKING_EXTRA_ALLOCATIONS" in result.stderr, result.stderr
            assert _version(url, database) == [revision]
            # Walmart's upgrade is in the same transaction and must also roll back.
            with _connect(url, database) as conn:
                assert not conn.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema='public' "
                    "AND table_name='fact_walmart_order_items' "
                    "AND column_name='is_identity_current'"
                ).fetchall()
        else:
            assert result.returncode == 0, result.stderr
            assert _version(url, database) == [HEAD]
            _exercise_stock(url, database, order_id, warehouse_read=True)
            denied = _alembic(url, database, revision, command="downgrade")
            assert denied.returncode != 0
            assert "PACKING_EXTRA_ALLOCATIONS_REQUIRE_VERIFIED_BACKUP_RESTORE" in denied.stderr
            assert _version(url, database) == [HEAD]
        with _connect(url, database) as conn:
            assert (
                conn.execute(
                    "SELECT to_jsonb(t)::text FROM ops_domestic_packing_extra_allocations t"
                ).fetchall()
                == before
            )
    finally:
        _drop(url, database)


def _seed_order(url, database):
    from app.db.model_registry import register_productlist_sync_models
    from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard
    from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder
    from app.modules.pmc_domestic.packing_schemas import Candidate

    register_productlist_sync_models()
    engine = sa.create_engine(url.set(database=database), hide_parameters=True)
    try:
        with Session(engine) as session:
            board = session.scalar(sa.select(DomesticInboundBoard))
            board.payload_json = {"available_good_num": 10, "purchase_order_sns": []}
            candidate = Candidate(
                id=uuid4(),
                candidate_version="a" * 64,
                source_account_ref=board.source_account_ref,
                warehouse_id=board.source_warehouse_id,
                publication_id=board.publication_id,
                board_id=board.id,
                inbound_order_sn=board.inbound_order_sn,
                sku=board.sku,
                product_name=None,
                store_id=None,
                store_name=None,
                item_id=None,
                gtin=None,
                msku=None,
                purchase_order_sns=[],
                arrival_purchased=None,
                candidate_created_on=None,
                overdue=None,
                stock_balance=10,
                available_quantity=10,
                default_quantity=None,
                can_approve=True,
                blocked_reasons=[],
                source_observed_at="2026-10-20T00:00:00Z",
            )
            order = PackingOrder(
                source_account_ref=board.source_account_ref,
                warehouse_id=board.source_warehouse_id,
                candidate_id=candidate.id,
                inbound_order_sn=board.inbound_order_sn,
                sku=board.sku,
                pk="PK-SYNTHETIC",
                qty=3,
                customs_src="default",
                is_test=True,
                status="approved",
                source_publication_id=board.publication_id,
                source_board_id=board.id,
                snapshot_json=candidate.model_dump(mode="json"),
                actor_uid="synthetic-test",
            )
            session.add(order)
            session.flush()
            session.add(
                PackingAllocation(
                    order_id=order.id,
                    source_account_ref=order.source_account_ref,
                    warehouse_id=order.warehouse_id,
                    source_board_id=board.id,
                    source_publication_id=board.publication_id,
                    qty=3,
                )
            )
            session.commit()
            return order.id
    finally:
        engine.dispose()


def _exercise_stock(url, database, order_id, *, warehouse_read):
    from app.modules.pmc_domestic.packing_models import PackingOrder
    from app.modules.pmc_domestic.packing_stock_repository import PackingStockRepository
    from app.modules.pmc_domestic.warehouse_schemas import WarehouseQuery
    from app.modules.pmc_domestic.warehouse_service import WarehouseService

    engine = sa.create_engine(url.set(database=database), hide_parameters=True)
    try:
        with Session(engine) as session:
            order = session.get(PackingOrder, order_id)
            repo = PackingStockRepository(session)
            budget = repo.budget(
                order.source_account_ref,
                order.warehouse_id,
                order.sku,
                excluding_extra_order=order.id,
            )
            assert budget.available == 7
            if not warehouse_read:
                repo.replace_extra(order, 2, budget)
                session.commit()
            assert (
                repo.budget(order.source_account_ref, order.warehouse_id, order.sku).available == 5
            )
            if warehouse_read:
                service = WarehouseService(session)
                listing = service.list(WarehouseQuery(), frozenset({order.source_account_ref}))
                assert listing.total == 1
                assert listing.items[0].extra_allocations[0].quantity == 2
                with pytest.raises(ValueError, match="insufficient"):
                    repo.replace_extra(order, 8, budget)
    finally:
        engine.dispose()


def test_0052_refuses_nonempty_ows_history_and_rolls_back():
    url = _admin_url()
    database = create_database(url, "ows_history")
    revision = "20261021_0051_domestic_packing_lifecycle"
    try:
        prepared = _alembic(url, database, revision)
        assert prepared.returncode == 0, prepared.stderr
        _seed_0049(url, database)
        order_id = _seed_order(url, database)
        with _connect(url, database) as conn:
            conn.execute(
                "INSERT INTO ops_domestic_packing_ows_links "
                "(id,order_id,source_account_ref,ows_no,is_current,actor_uid,note,created_at) "
                "VALUES (%s,%s,'synthetic-account','OWS-SYNTH',true,"
                "'synthetic','keep history',now())",
                (uuid4(), order_id),
            )
            before = conn.execute(
                "SELECT to_jsonb(t)::text FROM ops_domestic_packing_ows_links t"
            ).fetchall()
        result = _alembic(url, database, "head")
        assert result.returncode != 0
        assert "OWS_LINK_HISTORY_PRESENT_DO_NOT_DROP" in result.stderr
        assert _version(url, database) == [revision]
        with _connect(url, database) as conn:
            assert (
                conn.execute(
                    "SELECT to_jsonb(t)::text FROM ops_domestic_packing_ows_links t"
                ).fetchall()
                == before
            )
            assert conn.execute(
                "SELECT to_regclass('public.ops_domestic_packing_manual_requests')"
            ).fetchone() == (None,)
    finally:
        _drop(url, database)


def _assert_orm_tables(url, database):
    from app.db.base import Base
    from app.db.model_registry import register_productlist_sync_models

    register_productlist_sync_models()
    tables = {name for name in Base.metadata.tables if "_domestic_" in name}
    assert tables == set(DOMESTIC_TABLES)
    engine = sa.create_engine(url.set(database=database), hide_parameters=True)
    try:
        with engine.connect() as conn:
            for name in sorted(tables):
                conn.execute(sa.select(Base.metadata.tables[name]).limit(0)).all()
            _migration("0054")._require_current_shape(conn)
    finally:
        engine.dispose()
