"""Real PostgreSQL checks for the domestic chain through revision 0054.

The extra-allocation table is created by the existing merge revision. These tests
use disposable databases and synthetic rows only.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD = "20261022_0054_merge_walmart_identity_and_domestic_packing"
DOMESTIC_0049 = "20261020_0049_domestic_inbound_board"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
PROTECTED_DATABASES = frozenset({"szzsbj_dev", "szzsbj_test", "postgres", "szzsbj_app"})
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


def _admin_url() -> URL:
    if os.environ.get("DOMESTIC_CHAIN_DB_TESTS") != "1":
        pytest.skip("domestic chain PostgreSQL test requires explicit opt-in")
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        pytest.fail("TEST_DATABASE_URL is required for the domestic chain PostgreSQL test")
    url = make_url(raw)
    password = url.password or os.environ.get("PGPASSWORD")
    if url.host not in LOCAL_HOSTS or url.port not in {5432, 55432} or not password:
        pytest.fail("domestic chain tests refuse a non-local PostgreSQL target")
    return url.set(password=password)


def _connect(url: URL, database: str) -> psycopg.Connection:
    return psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=database,
        autocommit=True,
    )


def _recreate(url: URL, database: str) -> None:
    if database in PROTECTED_DATABASES or not database.startswith("szzsbj_chain_"):
        raise RuntimeError("refusing to recreate a protected database")
    with _connect(url, "postgres") as admin:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (database,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{database}"')
        admin.execute(f'CREATE DATABASE "{database}"')


def _drop(url: URL, database: str) -> None:
    if database in PROTECTED_DATABASES or not database.startswith("szzsbj_chain_"):
        return
    with _connect(url, "postgres") as admin:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (database,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


def _alembic(url: URL, database: str, revision: str) -> subprocess.CompletedProcess[str]:
    target = url.set(database=database)
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["TEST_DATABASE_URL"] = target.render_as_string(hide_password=False)
    env["PYTHONUTF8"] = "1"
    env.pop("PRODUCTION_MIGRATIONS_AUTHORIZED", None)
    return subprocess.run(
        ["uv", "run", "alembic", "upgrade", revision],
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
    database = "szzsbj_chain_empty"
    _recreate(url, database)
    try:
        first = _alembic(url, database, "head")
        assert first.returncode == 0, first.stderr
        assert _version(url, database) == [HEAD]
        assert _tables(url, database) == set(DOMESTIC_TABLES)
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
        assert "Running upgrade" not in second.stdout
        assert _version(url, database) == [HEAD]
    finally:
        _drop(url, database)


def test_database_at_0049_keeps_synthetic_rows_when_upgraded_to_0054() -> None:
    url = _admin_url()
    database = "szzsbj_chain_from_0049"
    _recreate(url, database)
    try:
        stopped = _alembic(url, database, DOMESTIC_0049)
        assert stopped.returncode == 0, stopped.stderr
        assert _version(url, database) == [DOMESTIC_0049]
        marker = _seed_0049(url, database)
        before = _counts(url, database)
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        assert _version(url, database) == [HEAD]
        assert _counts(url, database) == before
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
        assert "Running upgrade" not in repeated.stdout
        assert _counts(url, database) == before
    finally:
        _drop(url, database)


def test_existing_warehouse_tables_must_match_0053_before_upgrade() -> None:
    url = _admin_url()
    database = "szzsbj_chain_warehouse_shape"
    revision_0052 = "20261021_0052_domestic_packing_manual"
    revision_0053 = "20261022_0053_domestic_packing_production_compat"
    _recreate(url, database)
    try:
        created = _alembic(url, database, revision_0053)
        assert created.returncode == 0, created.stderr
        with _connect(url, database) as conn:
            conn.execute(
                "UPDATE alembic_version SET version_num = %s",
                (revision_0052,),
            )
        again = _alembic(url, database, revision_0053)
        assert again.returncode == 0, again.stderr
        assert _version(url, database) == [revision_0053]
        with _connect(url, database) as conn:
            conn.execute("DROP TABLE ops_domestic_packing_notification_outbox")
            conn.execute(
                "CREATE TABLE ops_domestic_packing_notification_outbox (id uuid PRIMARY KEY)"
            )
            conn.execute(
                "UPDATE alembic_version SET version_num = %s",
                (revision_0052,),
            )
        rejected = _alembic(url, database, revision_0053)
        assert rejected.returncode != 0
        assert "PACKING_WAREHOUSE_TABLE_SHAPE_MISMATCH" in rejected.stderr
        assert _version(url, database) == [revision_0052]
    finally:
        _drop(url, database)


def test_mismatched_extra_allocation_table_rejects_0054() -> None:
    url = _admin_url()
    database = "szzsbj_chain_mismatch"
    _recreate(url, database)
    try:
        prepared = _alembic(url, database, "20261022_0053_domestic_packing_production_compat")
        assert prepared.returncode == 0, prepared.stderr
        with _connect(url, database) as conn:
            conn.execute(
                "CREATE TABLE ops_domestic_packing_extra_allocations (id uuid PRIMARY KEY)"
            )
        rejected = _alembic(url, database, "head")
        assert rejected.returncode != 0
        assert "PACKING_EXTRA_ALLOCATIONS_COLUMNS_MISMATCH" in rejected.stderr
        assert _version(url, database) == ["20261022_0053_domestic_packing_production_compat"]
    finally:
        _drop(url, database)


def _counts(url: URL, database: str) -> dict[str, int]:
    names = (
        "ods_lingxing_domestic_warehouses",
        "dwd_domestic_receipt_batch",
        "dwd_domestic_receipt_batch_link",
        "gov_domestic_board_publications",
        "mart_domestic_inbound_batch_board",
    )
    with _connect(url, database) as conn:
        return {name: _count(conn, name) for name in names}


def _count(conn: psycopg.Connection, table_name: str) -> int:
    if table_name not in DOMESTIC_TABLES:
        raise RuntimeError("refusing to count an unknown table")
    row = conn.execute(f"SELECT count(*) FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])


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
                %s, %s, %s, 'synthetic-account', 0, '{}'::jsonb, %s, %s, 'synthetic-wh',
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
                %s, 'synthetic-account', 'synthetic-wh', 'published', true,
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
                %s, %s, 'synthetic-account', 'synthetic-wh', 'IB-SYNTH', 'SKU-SYNTH',
                'synthetic', '{}'::jsonb
            )
            """,
            (publication_id, board_id),
        )
    return publication_id
