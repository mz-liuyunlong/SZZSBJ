"""Persist Listing diagnostic runs, snapshots and confirmed C/D follow-up tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261027_0061_listing_evaluation_runs"
down_revision: str | Sequence[str] | None = "20261026_0060_merge_listing_business_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_listing_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("schedule_date_cn", sa.Date(), nullable=False),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("total_listings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_listings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("grade_candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lifecycle_candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blocked_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_dispatch_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("schedule_date_cn", name="uq_listing_evaluation_run_schedule_date"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')",
            name="ck_biz_listing_evaluation_runs_status",
        ),
        sa.CheckConstraint(
            "total_listings >= 0 AND processed_listings >= 0 "
            "AND grade_candidate_count >= 0 AND lifecycle_candidate_count >= 0 "
            "AND blocked_count >= 0 AND attempt_count >= 0",
            name="ck_biz_listing_evaluation_runs_nonnegative_counters",
        ),
    )
    op.create_index(
        "ix_listing_evaluation_runs_status_created",
        "biz_listing_evaluation_runs",
        ["status", "created_at"],
    )
    op.create_table(
        "biz_listing_evaluation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_listing_evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text()),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("current_lifecycle", sa.String(64)),
        sa.Column("current_grade", sa.String(64)),
        sa.Column("lifecycle_candidate", sa.String(64)),
        sa.Column("grade_candidate", sa.String(64)),
        sa.Column("valid_short", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_medium", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weighted_margin_percent", sa.Numeric(12, 6)),
        sa.Column("valid_stock_days_30", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observed_stock_days_7", sa.Integer(), server_default="0", nullable=False),
        sa.Column("low_stock_days_7", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "prior_effective_stock", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "currently_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("rule_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rule_source", sa.String(32), server_default="default", nullable=False),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("publication_status", sa.String(64), server_default="blocked", nullable=False),
        sa.Column("published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "listing_id", name="uq_listing_evaluation_snapshot_run_listing"
        ),
        sa.CheckConstraint(
            "valid_short >= 0 AND valid_medium >= 0",
            name="ck_biz_listing_evaluation_snapshots_valid_financial_days",
        ),
        sa.CheckConstraint(
            "observed_stock_days_7 >= 0 AND low_stock_days_7 >= 0 AND valid_stock_days_30 >= 0",
            name="ck_biz_listing_evaluation_snapshots_valid_stock_days",
        ),
    )
    op.create_index(
        "ix_listing_evaluation_snapshot_listing_cutoff",
        "biz_listing_evaluation_snapshots",
        ["listing_id", "cutoff_date_la"],
    )
    op.create_index(
        "ix_listing_evaluation_snapshot_grade",
        "biz_listing_evaluation_snapshots",
        ["cutoff_date_la", "grade_candidate"],
    )
    op.create_index(
        "ix_listing_evaluation_snapshot_scope",
        "biz_listing_evaluation_snapshots",
        ["run_id", "source_account_ref"],
    )
    op.create_table(
        "biz_listing_grade_follow_up_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_listing_evaluation_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text()),
        sa.Column("grade", sa.String(1), nullable=False),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("due_date_cn", sa.Date(), nullable=False),
        sa.Column("owner_ref", sa.String(255)),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("snapshot_id", name="uq_listing_grade_follow_up_snapshot"),
        sa.CheckConstraint(
            "grade IN ('C', 'D')", name="ck_biz_listing_grade_follow_up_tasks_grade_cd_only"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'canceled')",
            name="ck_biz_listing_grade_follow_up_tasks_status",
        ),
    )
    op.create_index(
        "ix_listing_grade_follow_up_owner_status_due",
        "biz_listing_grade_follow_up_tasks",
        ["owner_ref", "status", "due_date_cn"],
    )
    op.create_index(
        "ix_listing_grade_follow_up_scope",
        "biz_listing_grade_follow_up_tasks",
        ["source_account_ref", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listing_grade_follow_up_scope", table_name="biz_listing_grade_follow_up_tasks"
    )
    op.drop_index(
        "ix_listing_grade_follow_up_owner_status_due",
        table_name="biz_listing_grade_follow_up_tasks",
    )
    op.drop_table("biz_listing_grade_follow_up_tasks")
    op.drop_index(
        "ix_listing_evaluation_snapshot_scope", table_name="biz_listing_evaluation_snapshots"
    )
    op.drop_index(
        "ix_listing_evaluation_snapshot_grade", table_name="biz_listing_evaluation_snapshots"
    )
    op.drop_index(
        "ix_listing_evaluation_snapshot_listing_cutoff",
        table_name="biz_listing_evaluation_snapshots",
    )
    op.drop_table("biz_listing_evaluation_snapshots")
    op.drop_index(
        "ix_listing_evaluation_runs_status_created", table_name="biz_listing_evaluation_runs"
    )
    op.drop_table("biz_listing_evaluation_runs")
