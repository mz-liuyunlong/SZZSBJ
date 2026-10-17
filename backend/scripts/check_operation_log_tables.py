"""Read-only preflight: inspect actual DB tables and Alembic version.

This script never executes DDL/DML or prints sensitive record payloads.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_database_url


def main() -> None:
    names = (
        "business_rule_operation_logs",
        "legacy_mirror.event_ops_action_log",
        "legacy_mirror.biz_product_operation_log",
        "ops_system_operation_events",
        "ops_manual_operation_logs",
        "ops_operation_log_links",
    )
    engine = create_engine(get_database_url())
    with engine.connect() as connection:
        connection.execute(text("set transaction read only"))
        for name in names:
            present = connection.scalar(text("select to_regclass(:name) is not null"), {"name": name})
            print(f"{name}: {'exists' if present else 'missing'}")
        if connection.scalar(text("select to_regclass('public.alembic_version') is not null")):
            version = connection.scalar(text("select version_num from alembic_version"))
            print("alembic_version:", version)
        else:
            print("alembic_version: missing")
        connection.rollback()


if __name__ == "__main__":
    main()
