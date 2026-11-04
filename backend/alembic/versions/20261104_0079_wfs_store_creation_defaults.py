"""创建默认值按店铺（Rocky 2026-11-04）：新增 ``ref_wfs_store_creation_defaults``。

Frozen explicit DDL on a local MetaData with the project naming convention (same approach as
0077); ``tests/modules/pmc_wfs/test_store_defaults.py`` compares it with the ORM model.
No data is seeded: a store without a row falls back to the account row, then to 8088 defaults.
Downgrade refuses once a row exists.
"""

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261104_0079_wfs_store_creation_defaults"
down_revision = "20261104_0078_wfs_permissions"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
TABLE = "ref_wfs_store_creation_defaults"
J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def table(metadata: sa.MetaData) -> sa.Table:
    return sa.Table(
        TABLE,
        metadata,
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(64), primary_key=True),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("ship_date_offset", sa.Integer(), nullable=False),
        sa.Column("pallet_boxes", sa.Integer(), nullable=False),
        sa.Column("mixed_boxes", sa.Integer(), nullable=False),
        sa.Column("carrier_opt", sa.String(8), nullable=False),
        sa.Column("its", sa.Boolean(), nullable=False),
        sa.Column("return_address", J, nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transport IN ('LTL','SMALL_PARCEL','FTL')", name="wfs_store_default_transport"
        ),
        sa.CheckConstraint("carrier_opt IN ('own','wm')", name="wfs_store_default_carrier"),
        sa.CheckConstraint(
            "ship_date_offset >= 0 AND pallet_boxes >= 1 AND mixed_boxes >= 0",
            name="wfs_store_default_numbers",
        ),
    )


def upgrade() -> None:
    table(sa.MetaData(naming_convention=NAMING_CONVENTION)).create(
        bind=op.get_bind(), checkfirst=False
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(text(f"SELECT EXISTS (SELECT 1 FROM {TABLE})")).scalar():
        raise RuntimeError(f"{TABLE} has saved defaults; refusing to drop them")
    op.drop_table(TABLE)
