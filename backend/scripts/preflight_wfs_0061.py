"""Read-only production preflight for WFS migration 0061.

The command is default-deny, prints only schema/lock/count metadata, and never
executes DDL, DML, Alembic, or provider calls.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import Connection, create_engine, text

from app.core.config import get_database_url

BASE_REVISION = "20261026_0060_merge_listing_business_heads"
TARGET_REVISION = "20261026_0061_wfs_fee_detection_evidence"
REQUIRED_TABLES = (
    "gov_integration_sync_run_work_items",
    "gov_integration_sync_runs",
    "fact_walmart_wfs_fee_actual",
    "ops_wfs_fee_anomaly_cases",
    "ods_api_raw_request_refs",
)
NEW_TABLES = (
    "gov_wfs_settlement_collections",
    "ops_wfs_fee_detection_evidence",
)
NEW_COLUMNS = (
    ("gov_integration_sync_run_work_items", "scope_key"),
    ("fact_walmart_wfs_fee_actual", "platform_order_no"),
    ("fact_walmart_wfs_fee_actual", "sales_num"),
    ("fact_walmart_wfs_fee_actual", "platform_logistics_amount"),
    ("fact_walmart_wfs_fee_actual", "settlement_date"),
    ("fact_walmart_wfs_fee_actual", "source_raw_request_ref_id"),
    ("fact_walmart_wfs_fee_actual", "collection_id"),
    ("ops_wfs_fee_anomaly_cases", "valid_sample_units"),
    ("ops_wfs_fee_anomaly_cases", "valid_fee_orders"),
    ("ops_wfs_fee_anomaly_cases", "mode_count"),
    ("ops_wfs_fee_anomaly_cases", "theoretical_overcharge_amount"),
    ("ops_wfs_fee_anomaly_cases", "net_sample_difference_amount"),
    ("ops_wfs_fee_anomaly_cases", "latest_settlement_date"),
    ("ops_wfs_fee_anomaly_cases", "detection_status"),
    ("ops_wfs_fee_anomaly_cases", "data_freshness_status"),
    ("ops_wfs_fee_anomaly_cases", "standard_fee_source"),
    ("ops_wfs_fee_anomaly_cases", "detected_at"),
)


def _relation_exists(connection: Connection, relation: str) -> bool:
    return bool(
        connection.scalar(
            text("select to_regclass(:name) is not null"),
            {"name": f"public.{relation}"},
        )
    )


def _column_exists(connection: Connection, table_name: str, column_name: str) -> bool:
    return bool(
        connection.scalar(
            text(
                "select exists ("
                "select 1 from information_schema.columns "
                "where table_schema = 'public' and table_name = :table_name "
                "and column_name = :column_name)"
            ),
            {"table_name": table_name, "column_name": column_name},
        )
    )


def _duplicate_work_item_groups(connection: Connection, *, has_scope_key: bool) -> int:
    scope = ", scope_key" if has_scope_key else ""
    return int(
        connection.scalar(
            text(
                "select count(*) from ("
                "select run_id, request_kind"
                f"{scope}, offset_value "
                "from gov_integration_sync_run_work_items "
                "where request_kind = 'offset_page' "
                "group by run_id, request_kind"
                f"{scope}, offset_value having count(*) > 1) duplicate_groups"
            )
        )
        or 0
    )


def main() -> int:
    if os.getenv("WFS_0061_PREFLIGHT_ALLOW_DB_READ") != "YES":
        print("STOP: WFS_0061_PREFLIGHT_ALLOW_DB_READ_REQUIRED")
        return 2

    engine = create_engine(get_database_url())
    try:
        with engine.connect() as connection:
            connection.execute(text("set transaction read only"))
            connection.execute(text("set local lock_timeout = '3s'"))
            connection.execute(text("set local statement_timeout = '30s'"))

            database_name = connection.scalar(text("select current_database()"))
            server_version = connection.scalar(text("show server_version"))
            print("DATABASE_NAME:", database_name)
            print("POSTGRESQL_VERSION:", server_version)

            if not _relation_exists(connection, "alembic_version"):
                print("STOP: ALEMBIC_VERSION_TABLE_MISSING")
                connection.rollback()
                return 1
            revision = connection.scalar(text("select version_num from alembic_version"))
            print("ALEMBIC_REVISION:", revision)
            if revision not in {BASE_REVISION, TARGET_REVISION}:
                print("STOP: WFS_0061_UNEXPECTED_REVISION")
                connection.rollback()
                return 1

            missing = [name for name in REQUIRED_TABLES if not _relation_exists(connection, name)]
            print("REQUIRED_TABLES_MISSING:", len(missing))
            if missing:
                print("STOP: WFS_0061_BASE_SCHEMA_INCOMPLETE")
                connection.rollback()
                return 1

            for relation in REQUIRED_TABLES:
                size_bytes, estimated_rows = connection.execute(
                    text(
                        "select pg_total_relation_size(to_regclass(:name)), "
                        "coalesce((select reltuples::bigint from pg_class "
                        "where oid = to_regclass(:name)), 0)"
                    ),
                    {"name": f"public.{relation}"},
                ).one()
                print(
                    "RELATION_METADATA:",
                    relation,
                    f"bytes={int(size_bytes or 0)}",
                    f"estimated_rows={int(estimated_rows or 0)}",
                )

            has_scope_key = _column_exists(
                connection,
                "gov_integration_sync_run_work_items",
                "scope_key",
            )
            duplicate_groups = _duplicate_work_item_groups(
                connection,
                has_scope_key=has_scope_key,
            )
            print("WORK_ITEM_DUPLICATE_GROUPS:", duplicate_groups)

            index_definition = connection.scalar(
                text(
                    "select indexdef from pg_indexes "
                    "where schemaname = 'public' and tablename = "
                    "'gov_integration_sync_run_work_items' "
                    "and indexname = 'uq_gov_sync_work_offset'"
                )
            )
            print("WORK_ITEM_INDEX_PRESENT:", bool(index_definition))
            print("WORK_ITEM_SCOPE_KEY_PRESENT:", has_scope_key)

            new_table_count = sum(_relation_exists(connection, name) for name in NEW_TABLES)
            new_column_count = sum(
                _column_exists(connection, table_name, column_name)
                for table_name, column_name in NEW_COLUMNS
            )
            print("WFS_0061_NEW_TABLES_PRESENT:", new_table_count)
            print("WFS_0061_NEW_COLUMNS_PRESENT:", new_column_count)

            blocked_locks = int(
                connection.scalar(
                    text(
                        "select count(*) from pg_locks l "
                        "where not l.granted and l.relation in ("
                        "to_regclass('public.gov_integration_sync_run_work_items'), "
                        "to_regclass('public.gov_integration_sync_runs'), "
                        "to_regclass('public.fact_walmart_wfs_fee_actual'), "
                        "to_regclass('public.ops_wfs_fee_anomaly_cases'), "
                        "to_regclass('public.ods_api_raw_request_refs'), "
                        "to_regclass('public.gov_wfs_settlement_collections'), "
                        "to_regclass('public.ops_wfs_fee_detection_evidence'))"
                    )
                )
                or 0
            )
            long_transactions = int(
                connection.scalar(
                    text(
                        "select count(*) from pg_stat_activity "
                        "where datname = current_database() and pid <> pg_backend_pid() "
                        "and xact_start is not null "
                        "and clock_timestamp() - xact_start > interval '5 minutes'"
                    )
                )
                or 0
            )
            print("BLOCKED_TARGET_LOCKS:", blocked_locks)
            print("LONG_TRANSACTIONS_OVER_5M:", long_transactions)
            print("BACKUP_RESTORE_VERIFICATION: OWNER_DBA_REQUIRED")
            print("DISK_CAPACITY_VERIFICATION: SERVER_OPERATOR_REQUIRED")
            print("DATABASE_WRITES: 0")

            ready = (
                revision == BASE_REVISION
                and duplicate_groups == 0
                and new_table_count == 0
                and new_column_count == 0
                and bool(index_definition)
                and blocked_locks == 0
                and long_transactions == 0
            )
            already_applied = (
                revision == TARGET_REVISION
                and new_table_count == len(NEW_TABLES)
                and new_column_count == len(NEW_COLUMNS)
            )
            print(
                "PREFLIGHT_STATUS:",
                "READY_FOR_OWNER_WINDOW"
                if ready
                else "ALREADY_APPLIED"
                if already_applied
                else "BLOCKED",
            )
            connection.rollback()
            return 0 if ready or already_applied else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Do not reveal URLs, SQL parameters, business rows, or credentials.
        print("PREFLIGHT_FAILED_TYPE:", type(exc).__name__)
        sys.exit(1)
