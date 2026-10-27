"""Store long Skill references separately from compact runtime instructions.

The reference document remains available for review; only compact instructions are
sent to the model on each call.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261027_0064_ai_runtime_skill_context"
down_revision: str | Sequence[str] | None = "20261027_0063_ai_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_runtime_skill_versions",
        sa.Column("runtime_instructions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_runtime_skill_versions", "runtime_instructions")
