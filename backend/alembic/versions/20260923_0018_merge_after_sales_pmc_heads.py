"""Merge PMC Gate 3 and after-sales refund migration heads.

Revision ID: 20260923_0018_merge_after_sales_pmc_heads
Revises: 20260922_0017, 20260922_0017_after_sales_refund_amount
Create Date: 2026-09-23
"""

from collections.abc import Sequence

revision: str = "20260923_0018_merge_after_sales_pmc_heads"
down_revision: str | Sequence[str] | None = (
    "20260922_0017",
    "20260922_0017_after_sales_refund_amount",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
