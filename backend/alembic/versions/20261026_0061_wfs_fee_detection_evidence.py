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
    op.create_foreign_key(
        "fk_wfs_actual_raw_request_ref",
        "fact_walmart_wfs_fee_actual",
        "ods_api_raw_request_refs",
        ["source_raw_request_ref_id"],
        ["id"],
        ondelete="SET NULL",
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


def downgrade() -> None:
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
    op.drop_constraint(
        "fk_wfs_actual_raw_request_ref",
        "fact_walmart_wfs_fee_actual",
        type_="foreignkey",
    )
    for name in (
        "source_raw_request_ref_id",
        "settlement_date",
        "platform_logistics_amount",
        "sales_num",
        "platform_order_no",
    ):
        op.drop_column("fact_walmart_wfs_fee_actual", name)

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
