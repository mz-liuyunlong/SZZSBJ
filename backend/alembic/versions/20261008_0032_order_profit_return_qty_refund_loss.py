"""add order profit return quantity and refund loss

Revision ID: 20261008_0032_order_profit_return_qty_refund_loss
Revises: 20261008_0031_order_profit_sem_ad_spend
Create Date: 2026-10-08 17:48:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261008_0032_order_profit_return_qty_refund_loss"
down_revision: str | None = "20261008_0031_order_profit_sem_ad_spend"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mart_order_profit_sku_day",
        sa.Column("return_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "mart_order_profit_sku_day",
        sa.Column(
            "refund_loss_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "order_profit_return_qty_nonnegative",
        "mart_order_profit_sku_day",
        "return_qty >= 0",
    )
    op.create_check_constraint(
        "order_profit_refund_loss_amount_nonnegative",
        "mart_order_profit_sku_day",
        "refund_loss_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "order_profit_refund_loss_amount_nonnegative",
        "mart_order_profit_sku_day",
        type_="check",
    )
    op.drop_constraint(
        "order_profit_return_qty_nonnegative",
        "mart_order_profit_sku_day",
        type_="check",
    )
    op.drop_column("mart_order_profit_sku_day", "refund_loss_amount")
    op.drop_column("mart_order_profit_sku_day", "return_qty")
