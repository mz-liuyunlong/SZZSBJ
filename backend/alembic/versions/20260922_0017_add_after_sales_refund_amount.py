"""Add provider refund amount fields and clarify after-sales refund semantics.

Revision ID: 20260922_0017_after_sales_refund_amount
Revises: 20260922_0016_after_sales_refund_items_schema_repair
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0017_after_sales_refund_amount"
down_revision: str | None = "20260922_0016_after_sales_refund_items_schema_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "after_sales_refund_items",
        sa.Column(
            "refund_amount",
            sa.Numeric(18, 4),
            nullable=True,
            comment=(
                "平台退款金额：直接取 Walmart returnOrder/list "
                "items[].lineTotalAmount；不得乘 quantityDisplay。"
            ),
        ),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column(
            "refund_currency_code",
            sa.String(length=16),
            nullable=True,
            comment="平台退款币种：items[].lineTotalCurrency。",
        ),
    )

    op.execute(
        "comment on column after_sales_refund_items.refund_effective is "
        "'是否计入退款口径：items[].currentRefundStatus 为 "
        "NOT_REFUNDED/CANCELLED 时不计入；其他状态计入。'"
    )
    op.execute(
        """
        comment on column after_sales_refund_items.refund_loss_effective is
        '是否计入成本损失；当前仅 REFUND_COMPLETED=true。'
        """
    )


def downgrade() -> None:
    op.drop_column("after_sales_refund_items", "refund_currency_code")
    op.drop_column("after_sales_refund_items", "refund_amount")
