"""Add WFS actual fee facts and recovery case tracking.

Revision ID: 20260918_0015
Revises: 20260918_0014
Create Date: 2026-09-18

Schema only. This migration does not ingest Walmart bills or backfill data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260918_0015"
down_revision: str | Sequence[str] | None = "20260918_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_walmart_wfs_fee_actual",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("source_line_ref", sa.String(255), nullable=False),
        sa.Column("actual_fee_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="walmart_statement"),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref",
            "source_line_ref",
            name="uq_fact_walmart_wfs_fee_actual_source_line",
        ),
        sa.CheckConstraint("actual_fee_amount >= 0", name="ck_wfs_actual_fee_nonnegative"),
        sa.CheckConstraint("store_id <> ''", name="ck_wfs_actual_store_not_blank"),
        sa.CheckConstraint("item_id <> ''", name="ck_wfs_actual_item_not_blank"),
        sa.CheckConstraint("trim(msku) <> ''", name="ck_wfs_actual_msku_not_blank"),
    )
    op.create_index(
        "ix_fact_walmart_wfs_fee_actual_identity_date",
        "fact_walmart_wfs_fee_actual",
        ["source_account_ref", "business_date_la", "store_id", "item_id", "msku"],
    )

    op.create_table(
        "ops_wfs_fee_anomaly_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="未开Case"),
        sa.Column("case_no", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default="中"),
        sa.Column("claim_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("recovered_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("case_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_follow_at", sa.Date(), nullable=True),
        sa.Column("latest_follow", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref",
            "business_date_la",
            "store_id",
            "item_id",
            "msku",
            name="uq_ops_wfs_fee_anomaly_case_identity",
        ),
        sa.CheckConstraint(
            "status in ('未开Case','已开Case','跟进中','已追回','驳回','已关闭')",
            name="ck_wfs_case_status",
        ),
        sa.CheckConstraint("priority in ('高','中','低')", name="ck_wfs_case_priority"),
        sa.CheckConstraint("recovered_amount >= 0", name="ck_wfs_case_recovered_nonnegative"),
    )
    op.create_index(
        "ix_ops_wfs_fee_anomaly_cases_status",
        "ops_wfs_fee_anomaly_cases",
        ["source_account_ref", "status", "next_follow_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_wfs_fee_anomaly_cases_status", table_name="ops_wfs_fee_anomaly_cases")
    op.drop_table("ops_wfs_fee_anomaly_cases")
    op.drop_index(
        "ix_fact_walmart_wfs_fee_actual_identity_date",
        table_name="fact_walmart_wfs_fee_actual",
    )
    op.drop_table("fact_walmart_wfs_fee_actual")
