"""Finance journal: manual summary / memo text and split parts on line state."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261105_0078_finance_journal_edit_split"
down_revision: str | Sequence[str] | None = "20261105_0077_finance_approvals"
branch_labels = None
depends_on = None

TABLE = "manual_finance_cash_line_state"
EVENTS = "evt_finance_cash_line_reviews"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("manual_description", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("manual_memo", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    undone = bind.scalar(
        sa.text(f"SELECT count(*) FROM {EVENTS} WHERE kind IN ('review1_undo', 'review2_undo')")
    )
    if undone:
        raise RuntimeError(f"{EVENTS} 已有 {undone} 条撤销审核记录，拒绝降级")
    used = bind.scalar(
        sa.text(
            f"SELECT count(*) FROM {TABLE} "
            "WHERE manual_description IS NOT NULL OR manual_memo IS NOT NULL OR parts IS NOT NULL"
        )
    )
    if used:
        raise RuntimeError(f"{TABLE} 已有 {used} 行改过摘要 / 备注或拆分，拒绝降级")
    op.drop_column(TABLE, "parts")
    op.drop_column(TABLE, "manual_memo")
    op.drop_column(TABLE, "manual_description")
