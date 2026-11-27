"""0100 schema-only regression: no DB connection and no existing-table DDL."""

import io
import json
import re
import runpy
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
from app.modules.new_products import sku_ad_foundation_models  # noqa: F401

ROOT = Path(__file__).resolve().parents[4]
REV = "20261127_0100_sku_ad_progress_foundation"


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).strip()


def test_schema_only_and_orm_parity():
    manifest = json.loads(
        (ROOT / "PRPs/sku-ad-progress-foundation-field-map-0100.json").read_text()
    )
    names = set(manifest["tables"])
    assert len(names) == 16
    assert sum(len(fields) for fields in manifest["sku"].values()) == 524
    assert len(manifest["ad"]) == 51
    pending = ROOT / f"PRPs/pending-migrations/{REV}.py.pending"
    active = ROOT / f"backend/alembic/versions/{REV}.py"
    assert pending.exists() != active.exists()
    migration = runpy.run_path(str(active if active.exists() else pending))
    assert migration["revision"] == REV
    for fn in ("upgrade", "downgrade"):
        out = io.StringIO()
        ctx = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": out, "target_metadata": Base.metadata},
        )
        with Operations.context(ctx):
            migration[fn]()
        sql = out.getvalue()
        assert not re.search(
            r"\b(?:ALTER TABLE|INSERT INTO|UPDATE\s+\w+\s+SET|DELETE FROM|TRUNCATE)\b", sql, re.I
        )
        pattern = r"CREATE TABLE (\w+)" if fn == "upgrade" else r"DROP TABLE (\w+)"
        assert set(re.findall(pattern, sql)) == names
        if fn == "downgrade":
            assert set(migration["DOWNGRADE_TABLES"]) == names
            lock = sql.index("LOCK TABLE ")
            guard = sql.index("DO $sku_progress_rollback$")
            drop = sql.index("DROP TABLE ")
            assert lock < guard < drop
            for name in names:
                assert name in sql[lock:guard]
                assert f"IF EXISTS (SELECT 1 FROM {name})" in sql[guard:drop]
                assert f"0100 rollback blocked: {name} has data" in sql[guard:drop]
        if fn == "upgrade":
            assert "DROP TABLE" not in sql
            for name in names:
                table = Base.metadata.tables[name]
                assert all(fk.column.table.name in names for fk in table.foreign_keys)
                assert (
                    norm(str(CreateTable(table).compile(dialect=postgresql.dialect()))) + ";"
                    in norm(sql) + ";"
                )
                for index in table.indexes:
                    assert (
                        norm(str(CreateIndex(index).compile(dialect=postgresql.dialect()))) + ";"
                        in norm(sql) + ";"
                    )
