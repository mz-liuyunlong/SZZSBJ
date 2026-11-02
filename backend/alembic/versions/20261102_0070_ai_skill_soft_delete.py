"""Soft-delete AI Skill versions without breaking pinned keyword jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0070_ai_skill_soft_delete"
down_revision: str | Sequence[str] | None = "20261031_0069_walmart_gateway_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_runtime_skill_versions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_runtime_skill_versions", "deleted_at")
