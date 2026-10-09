"""add WFS low price delivery surcharge

Revision ID: 20261010_0033_add_wfs_low_price_surcharge
Revises: 20261008_0032_order_profit_return_qty_refund_loss
Create Date: 2026-10-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0033_add_wfs_low_price_surcharge"
down_revision: str | None = "20261008_0032_order_profit_return_qty_refund_loss"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mart_daily_sales_item_day",
        sa.Column(
            "wfs_low_price_surcharge_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mart_order_profit_sku_day",
        sa.Column(
            "wfs_low_price_surcharge_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "daily_sales_wfs_low_price_surcharge_nonnegative",
        "mart_daily_sales_item_day",
        "wfs_low_price_surcharge_amount >= 0",
    )
    op.create_check_constraint(
        "order_profit_wfs_low_price_surcharge_nonnegative",
        "mart_order_profit_sku_day",
        "wfs_low_price_surcharge_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "order_profit_wfs_low_price_surcharge_nonnegative",
        "mart_order_profit_sku_day",
        type_="check",
    )
    op.drop_constraint(
        "daily_sales_wfs_low_price_surcharge_nonnegative",
        "mart_daily_sales_item_day",
        type_="check",
    )
    op.drop_column("mart_order_profit_sku_day", "wfs_low_price_surcharge_amount")
    op.drop_column("mart_daily_sales_item_day", "wfs_low_price_surcharge_amount")
