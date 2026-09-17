"""Add exact provider order identifiers for refund matching.

Revision ID: 20260917_0013
Revises: 20260917_0012
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0013"
down_revision: str | Sequence[str] | None = "20260917_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fact_walmart_order_items",
        sa.Column("platform_order_no", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fact_walmart_order_items",
        sa.Column("reference_no", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_fact_walmart_order_items_platform_order_no",
        "fact_walmart_order_items",
        ["source_account_ref", "platform_order_no"],
        unique=False,
    )
    op.create_index(
        "ix_fact_walmart_order_items_reference_no",
        "fact_walmart_order_items",
        ["source_account_ref", "reference_no"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fact_walmart_order_items_reference_no",
        table_name="fact_walmart_order_items",
    )
    op.drop_index(
        "ix_fact_walmart_order_items_platform_order_no",
        table_name="fact_walmart_order_items",
    )
    op.drop_column("fact_walmart_order_items", "reference_no")
    op.drop_column("fact_walmart_order_items", "platform_order_no")
