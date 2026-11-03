"""Finance settlement profit V2 calculation columns (PRP §8.1 / §8.4, PR-3).

Small, additive change to the PR-1 tables (all still empty: PR-1 has no writer):
- adjustment kind ``assign_store`` and store mapping status ``manual_assigned`` for
  unmapped-store inventory movements (Rocky 2026-11-03);
- 待指定 rows can carry a ¥ amount, a reason, a detail payload and an assigned store;
- inventory movement rows keep the flow ``row_hash`` and their ``content_hash``;
- the store-month reconcile row keeps the result hash and the 入库运费 difference.
Downgrade restores the PR-1 shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0074_fin_settle_calc"
down_revision: str | Sequence[str] | None = "20261103_0072_fin_settle_profit_v2"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(precision=18, scale=4)
UNASSIGNED = "fact_settlement_unassigned_amounts"
MOVEMENTS = "fact_inventory_movement_lines"
ADJUSTMENTS = "manual_settlement_order_adjustments"
RECONCILE = "mart_settlement_reconcile_store_month"


def upgrade() -> None:
    op.drop_constraint("adjustment_kind", ADJUSTMENTS, type_="check")
    op.create_check_constraint(
        "adjustment_kind",
        ADJUSTMENTS,
        "kind IN ('cost', 'amount', 'assign_item', 'assign_store', 'note')",
    )

    op.drop_constraint("inv_move_store_mapping", MOVEMENTS, type_="check")
    op.drop_constraint("inv_move_store_id_matches_mapping", MOVEMENTS, type_="check")
    op.create_check_constraint(
        "inv_move_store_mapping",
        MOVEMENTS,
        "store_mapping_status IN ('mapped', 'unmapped', 'manual_assigned')",
    )
    op.create_check_constraint(
        "inv_move_store_id_matches_mapping",
        MOVEMENTS,
        "(store_mapping_status IN ('mapped', 'manual_assigned')) = (store_id IS NOT NULL)",
    )
    op.add_column(MOVEMENTS, sa.Column("source_row_hash", sa.String(length=64), nullable=False))
    op.add_column(MOVEMENTS, sa.Column("content_hash", sa.String(length=64), nullable=False))

    op.alter_column(UNASSIGNED, "amount_usd", existing_type=MONEY, nullable=True)
    op.add_column(UNASSIGNED, sa.Column("amount_cny", MONEY, nullable=True))
    op.add_column(
        UNASSIGNED,
        sa.Column(
            "reason",
            sa.String(length=32),
            server_default=sa.text("'unassigned'"),
            nullable=False,
        ),
    )
    op.add_column(
        UNASSIGNED,
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(UNASSIGNED, sa.Column("assigned_store_id", sa.String(length=128), nullable=True))
    op.drop_constraint("unassigned_assigned_has_item", UNASSIGNED, type_="check")
    op.create_check_constraint(
        "unassigned_assigned_has_target",
        UNASSIGNED,
        "status <> 'assigned' OR assigned_item_id IS NOT NULL OR assigned_store_id IS NOT NULL",
    )
    op.create_check_constraint(
        "unassigned_amount_present",
        UNASSIGNED,
        "amount_usd IS NOT NULL OR amount_cny IS NOT NULL",
    )

    op.add_column(
        RECONCILE, sa.Column("inbound_freight_lx_vs_settlement_diff_usd", MONEY, nullable=True)
    )
    op.add_column(RECONCILE, sa.Column("result_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column(RECONCILE, "result_hash")
    op.drop_column(RECONCILE, "inbound_freight_lx_vs_settlement_diff_usd")

    op.drop_constraint("unassigned_amount_present", UNASSIGNED, type_="check")
    op.drop_constraint("unassigned_assigned_has_target", UNASSIGNED, type_="check")
    op.execute(
        f"DELETE FROM {UNASSIGNED} WHERE amount_usd IS NULL OR assigned_store_id IS NOT NULL"
    )
    op.create_check_constraint(
        "unassigned_assigned_has_item",
        UNASSIGNED,
        "status <> 'assigned' OR assigned_item_id IS NOT NULL",
    )
    op.drop_column(UNASSIGNED, "assigned_store_id")
    op.drop_column(UNASSIGNED, "detail")
    op.drop_column(UNASSIGNED, "reason")
    op.drop_column(UNASSIGNED, "amount_cny")
    op.alter_column(UNASSIGNED, "amount_usd", existing_type=MONEY, nullable=False)

    op.drop_column(MOVEMENTS, "content_hash")
    op.drop_column(MOVEMENTS, "source_row_hash")
    op.execute(f"DELETE FROM {MOVEMENTS} WHERE store_mapping_status = 'manual_assigned'")
    op.drop_constraint("inv_move_store_id_matches_mapping", MOVEMENTS, type_="check")
    op.drop_constraint("inv_move_store_mapping", MOVEMENTS, type_="check")
    op.create_check_constraint(
        "inv_move_store_mapping", MOVEMENTS, "store_mapping_status IN ('mapped', 'unmapped')"
    )
    op.create_check_constraint(
        "inv_move_store_id_matches_mapping",
        MOVEMENTS,
        "(store_mapping_status = 'mapped') = (store_id IS NOT NULL)",
    )

    op.execute(f"DELETE FROM {ADJUSTMENTS} WHERE kind = 'assign_store'")
    op.drop_constraint("adjustment_kind", ADJUSTMENTS, type_="check")
    op.create_check_constraint(
        "adjustment_kind", ADJUSTMENTS, "kind IN ('cost', 'amount', 'assign_item', 'note')"
    )
