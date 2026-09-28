from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260928_0022_allow_negative_operation_plan_profit"
down_revision: str | None = "20260927_0021_operation_plan_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_ops_product_plan_profit_nonnegative",
        "ops_operation_product_plans",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_ops_product_plan_profit_nonnegative",
        "ops_operation_product_plans",
        "target_gross_profit_amount >= 0",
    )
