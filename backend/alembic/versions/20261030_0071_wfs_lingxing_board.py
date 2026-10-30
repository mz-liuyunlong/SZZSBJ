"""WFS shipment board fed from Lingxing: three append-only ODS tables, one published MART.

Tables are created from ORM metadata (same approach as 0049). No data collection, no
backfill, no permission grant. Downgrade refuses once any row exists so evidence is kept.
"""

from sqlalchemy import text

from alembic import op
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_wfs.lingxing_models import (
    LingxingWfsCargoGoodsOds,
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
    WfsBoardPublication,
    WfsShipmentBoardRow,
)

revision = "20261030_0071_wfs_lingxing_board"
down_revision = "20261030_0070_merge_wfs_walmart_remote"
branch_labels = None
depends_on = None

MODELS = (
    LingxingWfsCargoOds,
    LingxingWfsCargoGoodsOds,
    LingxingWfsShippingListOds,
    WfsBoardPublication,
    WfsShipmentBoardRow,
)


def upgrade() -> None:
    register_productlist_sync_models()
    bind = op.get_bind()
    for model in MODELS:
        model.__table__.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for model in MODELS:
        count = bind.execute(text(f"SELECT count(*) FROM {model.__tablename__}")).scalar()
        if count:
            raise RuntimeError(
                f"{model.__tablename__} has {count} rows; retain WFS evidence, use forward recovery"
            )
    for model in reversed(MODELS):
        model.__table__.drop(bind=bind, checkfirst=False)
