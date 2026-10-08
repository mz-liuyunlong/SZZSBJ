"""add order profit sem ad spend

Revision ID: 20261008_0031_order_profit_sem_ad_spend
Revises: 20261007_0030_daily_sales_sem_ad_spend
Create Date: 2026-10-08 11:36:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261008_0031_order_profit_sem_ad_spend"
down_revision: str | None = "20261007_0030_daily_sales_sem_ad_spend"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mart_order_profit_sku_day",
        sa.Column(
            "sem_ad_spend_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "order_profit_sem_ad_spend_amount_nonnegative",
        "mart_order_profit_sku_day",
        "sem_ad_spend_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "order_profit_sem_ad_spend_amount_nonnegative",
        "mart_order_profit_sku_day",
        type_="check",
    )
    op.drop_column("mart_order_profit_sku_day", "sem_ad_spend_amount")
