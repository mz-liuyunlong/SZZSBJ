"""Bring a throwaway schema cloned from the local development DB up to this branch's
WFS head by running the real migrations, never ORM create_all.

The development DB may sit on another branch's Alembic chain; tests must not depend on
which WFS migrations it happens to contain. Each step runs only when its marker is
missing, inside the caller's connection (search_path = the throwaway schema).
"""

import importlib.util
import os
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"

# CI-only target: the throwaway PostgreSQL service of the WFS integration job (282-04).
CI_DATABASE = "wfs_integration_ci"


def integration_target() -> tuple[URL, str]:
    """Database the opt-in WFS integration tests (``WFS_LOCAL_INTEGRATION=1``) may use.

    Exactly two targets are accepted; anything else is refused before connecting:
    - CI: ``WFS_CI_DATABASE_URL`` inside GitHub Actions (``CI`` and ``GITHUB_ACTIONS`` are
      ``true``), pointing at the job's own service ``127.0.0.1:5432/wfs_integration_ci``;
    - local: the verified development database (``scripts.wfs_pending_local_schema.local_url``,
      unchanged guard).
    Returns the URL and the database name callers assert after connecting.
    """
    ci_url = os.environ.get("WFS_CI_DATABASE_URL")
    if ci_url:
        if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
            raise RuntimeError("WFS_CI_DATABASE_URL is accepted only inside the CI job")
        url = make_url(ci_url)
        if not (
            url.drivername == "postgresql+psycopg"
            and url.host == "127.0.0.1"
            and url.port == 5432
            and url.database == CI_DATABASE
            and not url.query
        ):
            raise RuntimeError("Refusing database outside the CI-only WFS integration target")
        return url, CI_DATABASE
    from scripts.wfs_pending_local_schema import local_url

    return local_url(), "szzsbj_dev"


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


def table_structure(conn, schema: str, tables) -> dict:
    """Columns (type, nullability), PK / unique / FK (with ON DELETE) / check names and
    definitions, and indexes (with partial predicate) of ``tables`` in ``schema``."""
    import sqlalchemy as sa

    inspector = sa.inspect(conn)
    out = {}
    for name in sorted(tables):
        out[name] = {
            "columns": {
                c["name"]: (str(c["type"]), bool(c["nullable"]))
                for c in inspector.get_columns(name, schema=schema)
            },
            "pk": (
                inspector.get_pk_constraint(name, schema=schema)["name"],
                tuple(inspector.get_pk_constraint(name, schema=schema)["constrained_columns"]),
            ),
            "unique": sorted(
                (u["name"], tuple(u["column_names"]))
                for u in inspector.get_unique_constraints(name, schema=schema)
            ),
            "fk": sorted(
                (
                    f["name"],
                    tuple(f["constrained_columns"]),
                    f["referred_table"],
                    (f.get("options") or {}).get("ondelete"),
                )
                for f in inspector.get_foreign_keys(name, schema=schema)
            ),
            "check": sorted(
                (k["name"], k["sqltext"])
                for k in inspector.get_check_constraints(name, schema=schema)
            ),
            "indexes": sorted(
                (
                    i["name"],
                    tuple(i["column_names"]),
                    bool(i["unique"]),
                    str((i.get("dialect_options") or {}).get("postgresql_where")),
                )
                for i in inspector.get_indexes(name, schema=schema)
            ),
        }
    return out
