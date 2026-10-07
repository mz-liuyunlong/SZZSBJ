"""add daily sales sem ad spend

Revision ID: 20261007_0030_daily_sales_sem_ad_spend
Revises: 20261006_0029_legacy_selected_mirror_tables
Create Date: 2026-10-07 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261007_0030_daily_sales_sem_ad_spend"
down_revision: str | None = "20261006_0029_legacy_selected_mirror_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mart_daily_sales_item_day",
        sa.Column(
            "sem_ad_spend_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "sem_ad_spend_amount_nonnegative",
        "mart_daily_sales_item_day",
        "sem_ad_spend_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "sem_ad_spend_amount_nonnegative",
        "mart_daily_sales_item_day",
        type_="check",
    )
    op.drop_column("mart_daily_sales_item_day", "sem_ad_spend_amount")
