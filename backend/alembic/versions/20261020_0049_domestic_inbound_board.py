"""Separate procurement inbound board, stock publication, and warehouse statements.

No data collection, data backfill, permission grant or production execution.
"""

from alembic import op
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_domestic.inbound_models import (
    DomesticBoardPublication,
    DomesticInboundBoard,
    DomesticWarehouseStatement,
)

revision = "20261020_0049_domestic_inbound_board"
down_revision = "20261019_0048_domestic_warehouse_dwd_and_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    register_productlist_sync_models()
    bind = op.get_bind()
    for model in (DomesticWarehouseStatement, DomesticBoardPublication, DomesticInboundBoard):
        model.__table__.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    raise NotImplementedError("Retain inbound evidence; use reviewed forward recovery")
