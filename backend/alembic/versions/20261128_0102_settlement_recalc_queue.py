"""结算利润 V3：订单审核重算队列 settlement_recalc_queue（刘云龙 #377 终审）。

成本数据同步之后只重算受影响的 (店铺, 账期)，经这张表去重、串行：同一期同一时刻只有一个在算，
连续几次投递合并成一次，算的时候进来的新数据算完再补一次。只建这一张表，不碰 0101 及以前的任何对象。
回滚只删这张表：队列是可重建的工作记录，不是业务数据（没算完的期在页面「重算」即可补上）。

Revision ID: 20261128_0102_settlement_recalc_queue
Revises: 20261127_0101_finance_order_review_permissions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261128_0102_settlement_recalc_queue"
down_revision: str | Sequence[str] | None = "20261127_0101_finance_order_review_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "settlement_recalc_queue"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("period_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("claimed_generation", sa.Integer(), nullable=True),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(128), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        sa.CheckConstraint("generation >= 1", name="generation_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "source_account_ref", "store_id", "period_key", name="uq_settlement_recalc_queue"
        ),
    )
    op.create_index("ix_settlement_recalc_queue_status", TABLE, ["status", "requested_at"])


def downgrade() -> None:
    op.drop_index("ix_settlement_recalc_queue_status", table_name=TABLE)
    op.drop_table(TABLE)
