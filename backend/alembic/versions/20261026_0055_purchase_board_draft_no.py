"""Add draft_no parsed from purchase order line remarks to DWD/DWS.

Revision ID: 20261026_0055_purchase_board_draft_no
Revises: 20261022_0054_merge_walmart_identity_and_domestic_packing
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261026_0055_purchase_board_draft_no"
down_revision: str | Sequence[str] | None = "20261022_0054_merge_walmart_identity_and_domestic_packing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DWD_LINE = "dwd_purchase_order_line_item"
DWS_BOARD = "dws_purchase_board"
COLUMN = "draft_no"


def upgrade() -> None:
    op.add_column(DWD_LINE, sa.Column(COLUMN, sa.String(64), nullable=True))
    op.add_column(DWS_BOARD, sa.Column(COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column(DWS_BOARD, COLUMN)
    op.drop_column(DWD_LINE, COLUMN)
