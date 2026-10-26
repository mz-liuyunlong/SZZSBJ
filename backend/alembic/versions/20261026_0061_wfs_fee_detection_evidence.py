"""Add WFS order evidence and detection metrics.

Schema only. This migration does not collect provider data, backfill facts, create
cases, or enable a schedule.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261026_0061_wfs_fee_detection_evidence"
down_revision: str | Sequence[str] | None = "20261026_0060_merge_listing_business_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gov_integration_sync_run_work_items",
        sa.Column("scope_key", sa.String(255), server_default="", nullable=False),
    )
    op.drop_index(
        "uq_gov_sync_work_offset",
        table_name="gov_integration_sync_run_work_items",
    )
    op.create_index(
        "uq_gov_sync_work_offset",
        "gov_integration_sync_run_work_items",
        ["run_id", "request_kind", "scope_key", "offset_value"],
        unique=True,
        postgresql_where=sa.text("request_kind = 'offset_page'"),
    )

    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("platform_order_no", sa.String(255), nullable=True),
    )
    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("sales_num", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("platform_logistics_amount", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("settlement_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("source_raw_request_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "gov_wfs_settlement_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("collection_status", sa.String(32), nullable=False),
        sa.Column("wfs_scope_status", sa.String(32), server_default="unverified", nullable=False),
        sa.Column("expected_total", sa.Integer(), nullable=True),
        sa.Column("captured_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("business_excluded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_store_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_identity_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("verified_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latest_settlement_date", sa.Date(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "collection_status in ('running','verified','partial','failed')",
            name="ck_wfs_collection_status_allowed",
        ),
        sa.CheckConstraint(
            "wfs_scope_status in ('verified_wfs','unverified')",
            name="ck_wfs_collection_scope_allowed",
        ),
        sa.CheckConstraint(
            "expected_total is null or expected_total >= 0",
            name="ck_wfs_collection_expected_nonnegative",
        ),
        sa.CheckConstraint(
            "captured_count >= 0 and accepted_count >= 0 and "
            "business_excluded_count >= 0 and invalid_count >= 0 and "
            "missing_store_count >= 0 and duplicate_count >= 0 and "
            "missing_identity_count >= 0 and verified_count >= 0",
            name="ck_wfs_collection_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "source_account_ref",
            "store_id",
            "window_start",
            "window_end",
            name="uq_wfs_collection_run_scope_window",
        ),
    )
    op.create_index(
        "ix_wfs_collection_scope_window",
        "gov_wfs_settlement_collections",
        ["source_account_ref", "store_id", "window_start", "window_end", "collection_status"],
    )
    op.add_column(
        "fact_walmart_wfs_fee_actual",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_wfs_actual_raw_request_ref",
        "fact_walmart_wfs_fee_actual",
        "ods_api_raw_request_refs",
        ["source_raw_request_ref_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_wfs_actual_collection",
        "fact_walmart_wfs_fee_actual",
        "gov_wfs_settlement_collections",
        ["collection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fact_walmart_wfs_fee_actual_collection",
        "fact_walmart_wfs_fee_actual",
        ["collection_id", "store_id", "msku"],
    )
    op.create_index(
        "ix_fact_walmart_wfs_fee_actual_order",
        "fact_walmart_wfs_fee_actual",
        ["source_account_ref", "store_id", "msku", "platform_order_no"],
    )

    for name, column in (
        ("valid_sample_units", sa.Numeric(18, 4)),
        ("valid_fee_orders", sa.Integer()),
        ("mode_count", sa.Integer()),
        ("theoretical_overcharge_amount", sa.Numeric(14, 2)),
        ("net_sample_difference_amount", sa.Numeric(14, 2)),
        ("latest_settlement_date", sa.Date()),
        ("detection_status", sa.String(64)),
        ("data_freshness_status", sa.String(32)),
        ("standard_fee_source", sa.String(64)),
        ("detected_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("ops_wfs_fee_anomaly_cases", sa.Column(name, column, nullable=True))

    op.create_check_constraint(
        "ck_wfs_case_detection_metrics_nonnegative",
        "ops_wfs_fee_anomaly_cases",
        "(valid_sample_units IS NULL OR valid_sample_units >= 0) AND "
        "(valid_fee_orders IS NULL OR valid_fee_orders >= 0) AND "
        "(mode_count IS NULL OR mode_count >= 0) AND "
        "(theoretical_overcharge_amount IS NULL OR theoretical_overcharge_amount >= 0)",
    )

    op.create_table(
        "ops_wfs_fee_detection_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("actual_unit_fee", sa.Numeric(12, 4), nullable=False),
        sa.Column("standard_unit_fee", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_fee_diff", sa.Numeric(12, 4), nullable=False),
        sa.Column("sample_units", sa.Numeric(18, 4), nullable=False),
        sa.Column("sample_orders", sa.Integer(), nullable=False),
        sa.Column("mode_count", sa.Integer(), nullable=False),
        sa.Column("historical_units", sa.Numeric(18, 4), nullable=True),
        sa.Column("sales_start_date", sa.Date(), nullable=True),
        sa.Column("sales_end_date", sa.Date(), nullable=True),
        sa.Column("sales_coverage_status", sa.String(32), nullable=False),
        sa.Column("sales_coverage_reason", sa.String(128), nullable=False),
        sa.Column("sales_coverage_start_date", sa.Date(), nullable=True),
        sa.Column("sales_coverage_end_date", sa.Date(), nullable=True),
        sa.Column("sales_source_watermark", sa.String(255), nullable=True),
        sa.Column("legacy_estimated_overcharge", sa.Numeric(14, 2), nullable=True),
        sa.Column("theoretical_overcharge", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_sample_difference", sa.Numeric(14, 2), nullable=False),
        sa.Column("latest_settlement_date", sa.Date(), nullable=True),
        sa.Column("evidence_status", sa.String(64), nullable=False),
        sa.Column("fee_scope_status", sa.String(32), nullable=False),
        sa.Column("standard_fee_source", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("business_as_of_date", sa.Date(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_backtest", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actual_unit_fee >= 0 and standard_unit_fee >= 0 and unit_fee_diff >= 0",
            name="ck_wfs_evidence_fee_nonnegative",
        ),
        sa.CheckConstraint(
            "sample_units >= 0 and sample_orders >= 0 and mode_count >= 0",
            name="ck_wfs_evidence_samples_nonnegative",
        ),
        sa.CheckConstraint(
            "sales_coverage_status in ('complete','partial','missing','unknown')",
            name="ck_wfs_evidence_sales_coverage_allowed",
        ),
        sa.CheckConstraint(
            "fee_scope_status in ('verified_wfs','unverified')",
            name="ck_wfs_evidence_scope_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["gov_wfs_settlement_collections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["case_id"], ["ops_wfs_fee_anomaly_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id", "item_id", "msku", name="uq_wfs_detection_collection_item"
        ),
    )
    op.create_index(
        "ix_wfs_detection_evidence_latest",
        "ops_wfs_fee_detection_evidence",
        ["source_account_ref", "store_id", "item_id", "msku", "detected_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    evidence_count = bind.execute(
        sa.text("select count(*) from ops_wfs_fee_detection_evidence")
    ).scalar_one()
    collection_count = bind.execute(
        sa.text("select count(*) from gov_wfs_settlement_collections")
    ).scalar_one()
    if evidence_count or collection_count:
        raise RuntimeError("WFS_0061_DOWNGRADE_REQUIRES_EMPTY_NEW_TABLES")

    op.drop_index(
        "ix_wfs_detection_evidence_latest",
        table_name="ops_wfs_fee_detection_evidence",
    )
    op.drop_table("ops_wfs_fee_detection_evidence")
    op.drop_constraint(
        "ck_wfs_case_detection_metrics_nonnegative",
        "ops_wfs_fee_anomaly_cases",
        type_="check",
    )
    for name in (
        "detected_at",
        "standard_fee_source",
        "data_freshness_status",
        "detection_status",
        "latest_settlement_date",
        "net_sample_difference_amount",
        "theoretical_overcharge_amount",
        "mode_count",
        "valid_fee_orders",
        "valid_sample_units",
    ):
        op.drop_column("ops_wfs_fee_anomaly_cases", name)

    op.drop_index(
        "ix_fact_walmart_wfs_fee_actual_order",
        table_name="fact_walmart_wfs_fee_actual",
    )
    op.drop_index(
        "ix_fact_walmart_wfs_fee_actual_collection",
        table_name="fact_walmart_wfs_fee_actual",
    )
    op.drop_constraint(
        "fk_wfs_actual_collection",
        "fact_walmart_wfs_fee_actual",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_wfs_actual_raw_request_ref",
        "fact_walmart_wfs_fee_actual",
        type_="foreignkey",
    )
    for name in (
        "collection_id",
        "source_raw_request_ref_id",
        "settlement_date",
        "platform_logistics_amount",
        "sales_num",
        "platform_order_no",
    ):
        op.drop_column("fact_walmart_wfs_fee_actual", name)

    op.drop_index(
        "ix_wfs_collection_scope_window",
        table_name="gov_wfs_settlement_collections",
    )
    op.drop_table("gov_wfs_settlement_collections")

    op.drop_index(
        "uq_gov_sync_work_offset",
        table_name="gov_integration_sync_run_work_items",
    )
    op.create_index(
        "uq_gov_sync_work_offset",
        "gov_integration_sync_run_work_items",
        ["run_id", "request_kind", "offset_value"],
        unique=True,
        postgresql_where=sa.text("request_kind = 'offset_page'"),
    )
    op.drop_column("gov_integration_sync_run_work_items", "scope_key")
