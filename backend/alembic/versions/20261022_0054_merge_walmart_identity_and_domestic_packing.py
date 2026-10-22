"""Join the Walmart order-identity head with the domestic packing head.

Revision ID: 20261022_0054_merge_walmart_identity_and_domestic_packing
Revises: 20261020_0047_walmart_order_identity_guard,
          20261022_0053_domestic_packing_production_compat
Create Date: 2026-10-22

The merge keeps both existing revision ids. This revision also creates
ops_domestic_packing_extra_allocations. Databases already stamped here must
not rely on a later edit of this file.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.domestic_schema_contract import require_domestic_table

revision: str = "20261022_0054_merge_walmart_identity_and_domestic_packing"
down_revision: str | Sequence[str] | None = (
    "20261020_0047_walmart_order_identity_guard",
    "20261022_0053_domestic_packing_production_compat",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ops_domestic_packing_extra_allocations"
INDEX = "ix_packing_extra_source"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE, schema="public"):
        _require_current_shape(bind)
        return
    op.create_table(TABLE, *_elements())
    op.create_index(
        INDEX,
        TABLE,
        ["source_account_ref", "warehouse_id", "source_board_id"],
    )


def downgrade() -> None:
    # An adopted table may predate this revision. Never destroy it on downgrade.
    raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_REQUIRE_VERIFIED_BACKUP_RESTORE")


def _elements():
    return (
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("warehouse_id", sa.String(64), nullable=False),
        sa.Column("sku", sa.String(255), nullable=False),
        sa.Column("source_publication_id", sa.Uuid(), nullable=False),
        sa.Column("source_board_id", sa.Uuid(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("order_id", "source_board_id", name="uq_packing_extra_order_board"),
        sa.CheckConstraint("qty>0", name="packing_extra_qty"),
    )


def _require_current_shape(bind: sa.Connection) -> None:
    table = sa.Table(TABLE, sa.MetaData(), *_elements())
    sa.Index(INDEX, table.c.source_account_ref, table.c.warehouse_id, table.c.source_board_id)
    require_domestic_table(bind, table, prefix="PACKING_EXTRA_ALLOCATIONS")
