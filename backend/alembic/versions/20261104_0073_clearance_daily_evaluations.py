"""Persist daily LA-midnight WFS clearance evaluation runs and indexed Listing results.

Revision ID: 20261104_0073_clearance_daily
Revises: 20261104_0072_clearance_v1

All records are advisory analysis only. No Walmart action or approval is generated.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0073_clearance_daily"
down_revision: str | Sequence[str] | None = "20261104_0072_clearance_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_clearance_daily_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_date_la", sa.Date, nullable=False, unique=True),
        sa.Column("as_of_date_la", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("listing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("auto_high_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("auto_medium_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_required_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("quality_json", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("status in ('running','succeeded','partial','failed')",
                           name="ck_clearance_daily_run_status"),
        sa.CheckConstraint("attempt_count between 1 and 3", name="ck_clearance_daily_attempt"),
        sa.CheckConstraint("listing_count >= 0 and auto_high_count >= 0 and auto_medium_count >= 0",
                           name="ck_clearance_daily_counts"),
    )
    op.create_table(
        "ops_clearance_daily_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ops_clearance_daily_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("mart_listing_management_current.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("risk_level", sa.String(12), nullable=False),
        sa.Column("candidate_status", sa.String(24), nullable=False),
        sa.Column("stock_capital_usd", sa.Numeric(20, 4)),
        sa.Column("coverage_days", sa.Integer),
        sa.Column("profit_30d_amount", sa.Numeric(20, 4)),
        sa.Column("refund_loss_30d", sa.Numeric(20, 4)),
        sa.Column("quality_status", sa.String(20), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("rule_config_version", sa.Integer, nullable=False),
        sa.Column("evaluation_json", postgresql.JSONB, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "source_account_ref", "store_id", "item_id",
                            name="uq_clearance_daily_eval_identity"),
        sa.CheckConstraint("risk_level in ('high','medium','low','unknown')",
                           name="ck_clearance_daily_risk"),
        sa.CheckConstraint("quality_status in ('complete','partial','stale','unavailable')",
                           name="ck_clearance_daily_quality"),
    )
    op.create_index(
        "ix_clearance_daily_eval_page",
        "ops_clearance_daily_evaluations",
        ["run_id", "source_account_ref", "store_id", "risk_level",
         "candidate_status", "stock_capital_usd"],
    )
    op.create_index(
        "ix_clearance_daily_eval_listing",
        "ops_clearance_daily_evaluations",
        ["source_account_ref", "store_id", "item_id", "run_id"],
    )
    # Existing MART grain is item/day and store/day; account must lead every lookup.
    op.create_index("ix_clearance_daily_sales_identity",
                    "mart_daily_sales_item_day",
                    ["source_account_ref", "store_id", "item_id", "business_date_la"])
    op.create_index("ix_clearance_daily_wfs_identity",
                    "fact_walmart_listing_inventory_daily",
                    ["source_account_ref", "store_id", "item_id", "snapshot_date_la"])


def downgrade() -> None:
    op.drop_index("ix_clearance_daily_wfs_identity", table_name="fact_walmart_listing_inventory_daily")
    op.drop_index("ix_clearance_daily_sales_identity", table_name="mart_daily_sales_item_day")
    op.drop_index("ix_clearance_daily_eval_listing", table_name="ops_clearance_daily_evaluations")
    op.drop_index("ix_clearance_daily_eval_page", table_name="ops_clearance_daily_evaluations")
    op.drop_table("ops_clearance_daily_evaluations")
    op.drop_table("ops_clearance_daily_runs")
