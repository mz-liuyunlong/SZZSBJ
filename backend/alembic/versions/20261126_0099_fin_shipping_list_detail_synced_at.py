"""结算利润 PR-2：发货单表加「明细最近一次同步时间」列。

明细同步靠它判断一张发货单要不要（再）拉明细：为空或早于发货单的 updated_at 就拉。
明细为空的单子也会写这个时间，不会被反复重拉（#370 复审 P2-1）。

Revision ID: 20261126_0099_fin_shipping_list_detail_synced_at
Revises: 20261126_0098_wfs_cost_valuation_flow
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0099_fin_shipping_list_detail_synced_at"
down_revision: str | Sequence[str] | None = "20261126_0098_wfs_cost_valuation_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ods_lingxing_fin_shipping_lists"
COLUMN = "detail_synced_at"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # 只要有一张发货单记过明细同步时间就拒绝回滚、不删数据；生产要改结构一律写新的前向迁移。
    bind = op.get_bind()
    found = bind.execute(sa.text(f"select 1 from {TABLE} where {COLUMN} is not null limit 1"))
    if found.first() is not None:
        raise RuntimeError(f"rollback blocked: {TABLE}.{COLUMN} has data")
    op.drop_column(TABLE, COLUMN)
