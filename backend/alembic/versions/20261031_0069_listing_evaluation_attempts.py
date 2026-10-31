"""Preserve each Listing evaluation attempt and its diagnostic snapshots."""

from alembic import op

revision = "20261031_0069_listing_evaluation_attempts"
down_revision = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_listing_evaluation_run_schedule_date",
        "biz_listing_evaluation_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_listing_evaluation_run_date_attempt",
        "biz_listing_evaluation_runs",
        ["schedule_date_cn", "attempt_count"],
    )


def downgrade() -> None:
    # This fails safely if multiple attempts exist for one date: do not discard evidence.
    op.create_unique_constraint(
        "uq_listing_evaluation_run_schedule_date",
        "biz_listing_evaluation_runs",
        ["schedule_date_cn"],
    )
    op.drop_constraint(
        "uq_listing_evaluation_run_date_attempt",
        "biz_listing_evaluation_runs",
        type_="unique",
    )
