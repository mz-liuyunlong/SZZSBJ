"""0097：mart_walmart_bill_periods 加沃尔玛对账报表打款额（回款对账应付以沃尔玛为准）。

领星账单只含订单级交易，不含保证金扣留 / 释放等账户级交易；沃尔玛对账报表的 PaymentSummary
行才是实际打款。加 8 列，不建新表，不改既有行（payable_source 默认 lingxing）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261126_0097_walmart_bill_periods_recon_payout"
down_revision = "20261125_0096_settlement_profit_v3_tables"
branch_labels = None
depends_on = None

TABLE = "mart_walmart_bill_periods"
# 约束名和模型里 CheckConstraint(name=…) 一致（仓库其他表同样不带 ck_ 前缀）
CK_SOURCE = "payable_source"
CK_PAIR = "walmart_payable_source"
COLUMNS = (
    "walmart_total_payable",
    "walmart_diff",
    "payable_source",
    "walmart_period_start_date",
    "walmart_period_end_date",
    "walmart_posted_date",
    "walmart_account_rows",
    "walmart_synced_at",
)


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("walmart_total_payable", sa.Numeric(18, 4), nullable=True))
    op.add_column(TABLE, sa.Column("walmart_diff", sa.Numeric(18, 4), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "payable_source",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'lingxing'"),
        ),
    )
    op.add_column(TABLE, sa.Column("walmart_period_start_date", sa.Date(), nullable=True))
    op.add_column(TABLE, sa.Column("walmart_period_end_date", sa.Date(), nullable=True))
    op.add_column(TABLE, sa.Column("walmart_posted_date", sa.Date(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "walmart_account_rows",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(TABLE, sa.Column("walmart_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(CK_SOURCE, TABLE, "payable_source IN ('lingxing', 'walmart')")
    op.create_check_constraint(
        CK_PAIR, TABLE, "(payable_source = 'walmart') = (walmart_total_payable IS NOT NULL)"
    )


def downgrade() -> None:
    # 回滚只去掉这 8 列；有沃尔玛数据的期应付会退回领星口径，先确认财务已知。
    bind = op.get_bind()
    used = bind.scalar(sa.text(f"select count(*) from {TABLE} where payable_source = 'walmart'"))
    if used:
        raise RuntimeError(f"rollback blocked: {used} periods already use walmart payable")
    op.drop_constraint(CK_PAIR, TABLE, type_="check")
    op.drop_constraint(CK_SOURCE, TABLE, type_="check")
    for column in reversed(COLUMNS):
        op.drop_column(TABLE, column)
