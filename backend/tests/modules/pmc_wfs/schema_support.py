"""Bring a throwaway schema cloned from the local development DB up to this branch's
WFS head by running the real migrations, never ORM create_all.

The development DB may sit on another branch's Alembic chain; tests must not depend on
which WFS migrations it happens to contain. Each step runs only when its marker is
missing, inside the caller's connection (search_path = the throwaway schema).
"""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"


def run_migration(conn, filename: str, direction: str = "upgrade") -> None:
    spec = importlib.util.spec_from_file_location(f"wfs_mig_{filename[:13]}", VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, direction)()


def _has_table(conn, name: str) -> bool:
    return bool(conn.scalar(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name}))


def _has_column(conn, table: str, column: str) -> bool:
    return bool(
        conn.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE"
                " table_schema = current_schema() AND table_name = :t AND column_name = :c)"
            ),
            {"t": table, "c": column},
        )
    )


def ensure_manual_approval_columns(conn) -> None:
    """Migration 0073 when the cloned creation table predates it."""
    if not _has_column(conn, "ops_wfs_creation_operations", "approval_ref"):
        run_migration(conn, "20261101_0073_wfs_creation_manual_approval.py")


def bring_wfs_schema_to_head(conn) -> None:
    if not _has_table(conn, "ops_wfs_creation_operations"):
        run_migration(conn, "20261029_0068_wfs_creation.py")
    run_migration(conn, "20261101_0072_wfs_pending_drafts.py")  # adopts a complete set
    ensure_manual_approval_columns(conn)
