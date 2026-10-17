"""allow purchase-board ItemID source from_listing

Revision ID: 20261017_0043_purchase_board_listing_item_source
Revises: 20261017_0042_rbac_backfill
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261017_0043_purchase_board_listing_item_source"
down_revision: str | Sequence[str] | None = "20261017_0042_rbac_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_dws_purchase_board_item_id_source"
NEW_SQL = (
    "item_id_source IN ('from_system_plan', 'from_plan_remark', 'from_listing', "
    "'from_packing_slip', 'pending_packing_slip', 'unresolved')"
)
OLD_SQL = (
    "item_id_source IN ('from_system_plan', 'from_plan_remark', 'from_packing_slip', "
    "'pending_packing_slip', 'unresolved')"
)


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "dws_purchase_board", type_="check")
    op.create_check_constraint(CONSTRAINT, "dws_purchase_board", NEW_SQL)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "dws_purchase_board", type_="check")
    op.create_check_constraint(CONSTRAINT, "dws_purchase_board", OLD_SQL)
