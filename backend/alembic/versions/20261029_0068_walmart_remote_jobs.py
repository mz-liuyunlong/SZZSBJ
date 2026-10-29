"""Durable Walmart remote job state; does not enable execution or touch secrets."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0068_walmart_remote_jobs"
down_revision = "20261028_0067_merge_pmc_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "walmart_remote_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("store_code", sa.String(16), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("operations", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("run_id", sa.String(80)),
        sa.Column("files_verified", sa.Integer()),
        sa.Column("error_code", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "request_key",
            name="uq_walmart_remote_job_key",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','needs_review')",
            name="ck_walmart_remote_job_status",
        ),
    )
    op.create_index(
        "ix_walmart_remote_job_store", "walmart_remote_jobs", ["store_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_walmart_remote_job_store", table_name="walmart_remote_jobs")
    op.drop_table("walmart_remote_jobs")
