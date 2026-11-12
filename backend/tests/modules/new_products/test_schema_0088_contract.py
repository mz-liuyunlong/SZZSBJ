"""Read-only PR337 schema contract checks; no live database or Alembic upgrade.

The migration intentionally stores facts but does not infer inventory/return rules.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"


def load_migration(path: Path):
    spec = spec_from_file_location("np_schema_" + path.stem, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema_tables():
    meta = sa.MetaData()
    tables = {}
    indexes = {}

    def create_table(name, *cols, **kwargs):
        tables[name] = sa.Table(name, meta, *cols, **kwargs)
        return tables[name]

    def create_index(name, table, columns, **kwargs):
        assert name not in indexes
        idx = sa.Index(name, *(tables[table].c[c] for c in columns), **kwargs)
        indexes[name] = idx
        return idx

    def add_column(table, col):
        tables[table].append_column(col)

    for migration_path in (
        VERSIONS / "20261112_0087_new_product_performance.py",
        VERSIONS / "20261112_0088_new_product_tracking_foundation.py",
    ):
        migration = load_migration(migration_path)
        with (
            patch.object(migration.op, "create_table", create_table),
            patch.object(migration.op, "create_index", create_index),
            patch.object(migration.op, "add_column", add_column),
        ):
            migration.upgrade()

    # Postgres DDL compilation verifies all FK targets resolve; this does not
    # connect to any database and creates no tables.
    dialect = postgresql.dialect()
    for table in tables.values():
        str(CreateTable(table).compile(dialect=dialect))
    for index in indexes.values():
        str(CreateIndex(index).compile(dialect=dialect))
    return tables, indexes


def test_migration_chain_and_11_business_tables():
    current = load_migration(VERSIONS / "20261112_0088_new_product_tracking_foundation.py")
    assert current.down_revision == "20261112_0087_new_product_performance"
    tables, _ = schema_tables()
    assert set(tables) == {
        "biz_new_product_rule_versions",
        "biz_new_product_market_scores",
        "biz_new_product_purchase_applications",
        "biz_new_product_tracking_decisions",
        "biz_new_product_action_events",
        "biz_new_product_registry",
        "biz_new_product_performance_current",
        "biz_new_product_tracking_current",
        "biz_new_product_daily_snapshots",
        "biz_new_product_tracking_review_applications",
        "biz_new_product_replenishment_applications",
    }


def test_required_data_fields_and_pending_review_guard():
    tables, indexes = schema_tables()
    registry = tables["biz_new_product_registry"].c
    assert {
        "source_account_ref",
        "store_id",
        "item_id",
        "image_url",
        "product_name",
        "sku",
        "msku",
        "store_name",
        "owner_name",
        "category_l1",
        "listing_date_la",
    } <= set(registry.keys())
    perf = tables["biz_new_product_performance_current"].c
    assert {
        "first_batch_sold_out_date_la",
        "sold_out_evidence_json",
        "first_order_date_la",
        "ad_spend_usd",
        "ad_clicks",
        "ad_spend_ratio_pct",
        "sample_units",
        "sample_amount_usd",
        "return_rate_units_pct",
        "return_rate_orders_pct",
        "return_reasons_json",
        "profit_usd",
        "roi",
        "profit_margin_pct",
        "grade",
        "process_status",
    } <= set(perf.keys())
    tracking = tables["biz_new_product_tracking_current"].c
    assert {
        "purchase_submitted_at",
        "first_domestic_arrival_at",
        "full_domestic_arrival_at",
        "domestic_dispatched_at",
        "tracking_started_date_la",
        "tracking_start_evidence_json",
        "initial_grade",
        "purchase_approved_qty",
        "trend_7d_json",
        "trend_14d_json",
        "trend_30d_json",
        "return_rate_units_pct",
        "return_rate_orders_pct",
        "return_reasons_json",
        "final_result",
        "triggered_rules_json",
    } <= set(tracking.keys())
    review = tables["biz_new_product_tracking_review_applications"].c
    assert {
        "proposed_result",
        "status",
        "applicant_reason",
        "facts_snapshot_json",
        "reviewed_by",
        "reviewed_at",
        "review_reason",
        "approval_request_ref",
    } <= set(review.keys())
    purchase = tables["biz_new_product_purchase_applications"].c
    assert {"approved_qty", "approval_request_ref"} <= set(purchase.keys())
    assert indexes["uq_np_review_pending"].unique
    assert (
        str(indexes["uq_np_review_pending"].dialect_options["postgresql"]["where"])
        == "status = 'submitted'"
    )


def test_schema_has_no_automatic_jobs_or_seeded_business_decisions():
    migration_source = (VERSIONS / "20261112_0088_new_product_tracking_foundation.py").read_text()
    assert "op.execute(" not in migration_source
    assert "insert into" not in migration_source.lower()
    assert "create_trigger" not in migration_source.lower()
