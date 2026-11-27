"""Finance journal: manual RMB amount on a line and closing journal alerts with a reason."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_0086_finance_journal_cny_alert_close"
down_revision: str | Sequence[str] | None = "20261110_0085_finance_payout_recon"
branch_labels = None
depends_on = None

STATE = "manual_finance_cash_line_state"
CLOSURES = "manual_finance_cash_alert_closures"


def upgrade() -> None:
    # 人工改的折人民币（Rocky 11-10：约定汇率每笔不同，财务直接改，必须写原因）。
    op.add_column(STATE, sa.Column("manual_amount_cny", sa.Numeric(18, 4), nullable=True))
    op.add_column(STATE, sa.Column("manual_cny_reason", sa.Text(), nullable=True))
    # 关闭异常：一条异常一个 key（类型 | 流水号 / 审批单号 / 剔除清单号）；
    # 关闭要写原因，可以重新打开。
    op.create_table(
        CLOSURES,
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("alert_key", sa.String(200), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("closed_by", sa.String(255), nullable=False),
        sa.Column(
            "closed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("reopened_by", sa.String(255), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "uq_manual_finance_cash_alert_closures_open",
        CLOSURES,
        ["alert_key"],
        unique=True,
        postgresql_where=sa.text("reopened_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    closed = bind.scalar(sa.text(f"SELECT count(*) FROM {CLOSURES}"))
    if closed:
        raise RuntimeError(f"{CLOSURES} 已有 {closed} 条关闭异常记录，拒绝降级")
    changed = bind.scalar(
        sa.text(f"SELECT count(*) FROM {STATE} WHERE manual_amount_cny IS NOT NULL")
    )
    if changed:
        raise RuntimeError(f"{STATE} 已有 {changed} 行人工改过折人民币，拒绝降级")
    op.drop_index("uq_manual_finance_cash_alert_closures_open", table_name=CLOSURES)
    op.drop_table(CLOSURES)
    op.drop_column(STATE, "manual_cny_reason")
    op.drop_column(STATE, "manual_amount_cny")
