"""Add refund loss date to after sales refund items.

Revision ID: 20260922_0015_add_after_sales_refund_loss_date
Revises: 20260922_0014_after_sales_refund_items
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0015_add_after_sales_refund_loss_date"
down_revision: str | None = "20260922_0014_after_sales_refund_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "after_sales_refund_items",
        sa.Column("refund_loss_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_after_sales_refund_items_loss_date",
        "after_sales_refund_items",
        ["refund_loss_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_after_sales_refund_items_loss_date",
        table_name="after_sales_refund_items",
    )
    op.drop_column("after_sales_refund_items", "refund_loss_date")
