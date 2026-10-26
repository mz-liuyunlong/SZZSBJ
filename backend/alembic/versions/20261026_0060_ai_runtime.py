"""Durable, scoped AI job, skill and conversation records; no data migration/backfill.

Requires separate review and database authorization before applying.
"""
from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "20261026_0060_ai_runtime"
down_revision: str | Sequence[str] | None = "20261025_0059_business_connector_control"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("ai_runtime_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("request_key", sa.String(255), nullable=False),
        sa.Column("input_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("phase", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','partial_success')", name="ck_ai_runtime_jobs_status"),
        sa.UniqueConstraint("source_account_ref", "request_key", name="uq_ai_runtime_jobs_idempotency"),
    )
    op.create_index("ix_ai_runtime_jobs_owner", "ai_runtime_jobs", ["source_account_ref","requested_by","created_at"])
    op.create_table("ai_runtime_results",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_runtime_jobs.id",ondelete="CASCADE"), nullable=False),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("output_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("job_id","batch_index"),
    )
    op.create_table("ai_runtime_skill_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("biz_connectors.id",ondelete="RESTRICT"), nullable=False),
        sa.Column("scene", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft','published','retired')", name="ck_ai_runtime_skill_status"),
        sa.UniqueConstraint("connector_id","scene","version", name="uq_ai_runtime_skill_version"),
    )
    op.create_table("ai_runtime_chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table("ai_runtime_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_runtime_chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_ai_runtime_chat_role"),
    )

def downgrade() -> None:
    op.drop_table("ai_runtime_chat_messages")
    op.drop_table("ai_runtime_chats")
    op.drop_table("ai_runtime_skill_versions")
    op.drop_table("ai_runtime_results")
    op.drop_index("ix_ai_runtime_jobs_owner",table_name="ai_runtime_jobs")
    op.drop_table("ai_runtime_jobs")
