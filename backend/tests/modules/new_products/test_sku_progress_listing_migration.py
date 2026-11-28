"""Offline 0103 DDL and synthetic historical mapping; no external database."""

import importlib.util
import io
import re
import sqlite3
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migration_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/20261128_0103_sku_purchase_listing_identity.py"
    )
    spec = importlib.util.spec_from_file_location("sku_purchase_0103", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_and_downgrade_ddl_offline():
    migration = migration_module()
    assert migration.down_revision == "20261128_0102_woocommerce_store_config"
    assert not text(migration.BACKFILL)._bindparams
    for direction in ("upgrade", "downgrade"):
        buf = io.StringIO()
        ctx = MigrationContext.configure(
            dialect_name="postgresql",
            opts={
                "as_sql": True,
                "output_buffer": buf,
            },
        )
        with Operations.context(ctx):
            getattr(migration, direction)()
        ddl = buf.getvalue()
        assert "ACCESS EXCLUSIVE MODE" in ddl
        if direction == "upgrade":
            assert "ADD COLUMN item_id" in ddl
            assert "uq_sku_purchase_active_listing" in ddl
            assert "uq_sku_purchase_active_legacy_store" in ddl
            assert "NOT VALID" in ddl
        else:
            assert ddl.index("SKU_PURCHASE_LISTING_DOWNGRADE_BLOCKED_NONEMPTY") < ddl.index(
                "DROP COLUMN item_id"
            )
        assert "DROP TABLE" not in ddl and "DELETE FROM" not in ddl


def test_historical_attribution_requires_single_exact_event():
    # Execute the same backfill relational logic on synthetic rows. Adapt only
    # the PostgreSQL cast, regex and aggregate syntax for SQLite compatibility.
    import json

    class BoolAnd:
        def __init__(self):
            self.valid = True

        def step(self, value):
            self.valid = self.valid and bool(value)

        def finalize(self):
            return int(self.valid)

    migration = migration_module()
    sql = migration.BACKFILL.replace("p.id::text", "CAST(p.id AS text)")
    sql = sql.replace(" ~ ", " REGEXP ")
    with sqlite3.connect(":memory:") as db:
        db.create_function("chr", 1, chr)
        db.create_function(
            "regexp",
            2,
            lambda pattern, value: bool(value is not None and re.fullmatch(pattern, value)),
        )
        db.create_aggregate("bool_and", 1, BoolAnd)
        db.executescript("""
        CREATE TABLE biz_new_product_sku_purchase_plans(
          id text,sku_progress_id text,store_id text,item_id text);
        CREATE TABLE biz_new_product_sku_progress_events(
          sku_progress_id text,event_key text,event_type text,after_json text);
        """)
        claims = [(str(i), "sku", "S", None) for i in range(1, 9)]
        db.executemany("INSERT INTO biz_new_product_sku_purchase_plans VALUES(?,?,?,?)", claims)
        events = [
            ("1", "sku", "S", "12345678901"),  # exact
            ("2", "sku", "T", "22345678901"),  # wrong store
            ("3", "other", "S", "32345678901"),  # wrong progress
            ("4", "sku", "S", "bad"),
            ("5", "sku", "S", "52345678901"),
            ("6", "sku", "S", "52345678901"),  # duplicate claim mapping
            ("7", "sku", "S", "72345678901"),
            ("7", "sku", "S", "82345678901"),  # ambiguous event
            # 8: missing event
        ]
        db.executemany(
            "INSERT INTO biz_new_product_sku_progress_events VALUES(?,?,?,?)",
            [
                (
                    progress,
                    plan + ":attempt",
                    "purchase_attempt",
                    json.dumps({"store_id": store, "item_id": item}),
                )
                for plan, progress, store, item in events
            ],
        )
        db.execute(sql)
        rows = dict(db.execute("SELECT id,item_id FROM biz_new_product_sku_purchase_plans"))
        assert rows == {str(i): "12345678901" if i == 1 else None for i in range(1, 9)}
