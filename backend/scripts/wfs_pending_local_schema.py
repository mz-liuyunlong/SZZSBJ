"""Owner-approved additive local setup; never alters Alembic history or existing business rows.

Default is inspection only. --apply creates exactly four WFS-owned tables in the
verified local development database, in one transaction; no broad create_all.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.modules.pmc_domestic import inbound_models, warehouse_models  # noqa: E402, F401
from app.modules.pmc_wfs.repository import WFS_TABLES  # noqa: E402


def local_url():
    # Match the existing local launcher without displaying any credential values.
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if "DATABASE_URL" not in os.environ and env_file.exists():
        for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))
    url = make_url(os.environ["DATABASE_URL"])
    if not (
        os.environ.get("APP_ENV") == "local"
        and url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 55432
        and url.database == "szzsbj_dev"
        and not url.query
    ):
        raise RuntimeError("Refusing database outside approved local development target")
    return url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = create_engine(local_url(), hide_parameters=True)
    with engine.begin() as conn:
        identity = conn.execute(text("select current_database(), inet_server_port()")).one()
        if identity[0] != "szzsbj_dev":
            raise RuntimeError("Connected database identity mismatch")
        conn.execute(text("SET LOCAL lock_timeout='5s'"))
        conn.execute(text("SELECT pg_advisory_xact_lock(720261023)"))
        tables = set(inspect(conn).get_table_names())
        protected = [
            "ops_domestic_packing_orders",
            "ops_domestic_packing_box_sets",
            "ops_domestic_packing_box_lines",
            "evt_domestic_packing_events",
        ]
        if not set(protected).issubset(tables):
            raise RuntimeError("Domestic prerequisites missing")
        before = {name: conn.scalar(text(f'SELECT count(*) FROM "{name}"')) for name in protected}
        revision = list(conn.scalars(text("select version_num from alembic_version")))
        existing = [t.name for t in WFS_TABLES if t.name in tables]
        wfs_counts = {
            name: conn.scalar(text(f'SELECT count(*) FROM "{name}"')) for name in existing
        }
        print(
            json.dumps(
                {
                    "database": identity[0],
                    "domestic_counts": before,
                    "alembic_revision": revision,
                    "wfs_existing": existing,
                    "wfs_counts": wfs_counts,
                }
            )
        )
        if args.apply:
            if existing:
                raise RuntimeError("WFS tables already exist; inspect drift, do not overwrite")
            for table in WFS_TABLES:
                table.create(conn)
            conn.execute(
                text("""
                CREATE FUNCTION prevent_pmc_wfs_event_mutation() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'WFS events are immutable'; END;
                $$ LANGUAGE plpgsql
            """)
            )
            conn.execute(
                text("""
                CREATE TRIGGER pmc_wfs_events_immutable BEFORE UPDATE OR DELETE
                ON evt_pmc_wfs_draft_events FOR EACH ROW
                EXECUTE FUNCTION prevent_pmc_wfs_event_mutation()
            """)
            )
            after = {
                name: conn.scalar(text(f'SELECT count(*) FROM "{name}"')) for name in protected
            }
            if (
                after != before
                or list(conn.scalars(text("select version_num from alembic_version"))) != revision
            ):
                raise RuntimeError("Existing data or migration history changed; rolling back")
            print("CREATED_FOUR_WFS_TABLES_EXISTING_COUNTS_AND_REVISION_UNCHANGED")
    engine.dispose()


if __name__ == "__main__":
    main()
