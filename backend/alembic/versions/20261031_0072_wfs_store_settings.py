"""Per-store WFS creation settings (Walmart store code, ITS availability, master switch).

Created from ORM metadata; no data, no permission grant. Downgrade refuses once rows exist.
"""

from sqlalchemy import text

from alembic import op
from app.modules.pmc_wfs.store_settings_models import WfsStoreSetting

revision = "20261031_0072_wfs_store_settings"
down_revision = "20261030_0071_wfs_lingxing_board"
branch_labels = None
depends_on = None


def upgrade() -> None:
    WfsStoreSetting.__table__.create(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(text("SELECT count(*) FROM ops_wfs_store_settings")).scalar():
        raise RuntimeError("ops_wfs_store_settings has rows; refusing to drop evidence")
    WfsStoreSetting.__table__.drop(bind=bind, checkfirst=False)
