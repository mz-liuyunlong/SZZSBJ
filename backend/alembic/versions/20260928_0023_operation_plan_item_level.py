from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260928_0023_operation_plan_item_level"
down_revision: str | None = "20260928_0022_allow_negative_operation_plan_profit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            do $$
            begin
                if exists (
                    select 1
                    from ops_operation_product_plans
                    group by period_id, platform_code, item_id
                    having count(*) > 1
                ) then
                    raise exception
                        'duplicate item_id plans';
                end if;
            end $$;
            """
        )
    )

    op.drop_constraint(
        "uq_ops_product_plan_identity",
        "ops_operation_product_plans",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_ops_product_plan_item_identity",
        "ops_operation_product_plans",
        ["period_id", "platform_code", "item_id"],
    )

    op.create_index(
        "ix_ops_product_plans_period_item",
        "ops_operation_product_plans",
        ["period_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_product_plans_period_item", table_name="ops_operation_product_plans")

    op.drop_constraint(
        "uq_ops_product_plan_item_identity",
        "ops_operation_product_plans",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_ops_product_plan_identity",
        "ops_operation_product_plans",
        ["period_id", "platform_code", "source_account_ref", "item_id", "msku"],
    )
