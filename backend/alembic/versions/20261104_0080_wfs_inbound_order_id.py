"""WFS 单号（Rocky 2026-11-04）：计划货件加 ``inbound_order_id``，格式同 8088。

``PMC-<店铺码>-<YYYYMMDD>-<序号>``（如 PMC-HK2614-20261015-01），首次提交 Walmart 前分配，
之后重试、查询都用同一个单号；领星的入库订单编号也等于它。可空（未提交的票没有单号），
唯一。Downgrade refuses once a ticket has an order id.
"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "20261104_0080_wfs_inbound_order_id"
down_revision = "20261104_0079_wfs_store_creation_defaults"
branch_labels = None
depends_on = None

TABLE = "ops_wfs_creation_tickets"
COLUMN = "inbound_order_id"
CONSTRAINT = "uq_ops_wfs_creation_tickets_inbound_order_id"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(40), nullable=True))
    op.create_unique_constraint(CONSTRAINT, TABLE, [COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        text(f"SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE {COLUMN} IS NOT NULL)")
    ).scalar()
    if used:
        raise RuntimeError(f"{TABLE}.{COLUMN} is in use; refusing to drop it")
    op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
    op.drop_column(TABLE, COLUMN)
