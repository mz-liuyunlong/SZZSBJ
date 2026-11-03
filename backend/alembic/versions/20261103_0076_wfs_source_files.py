"""WFS file-sourced facts: RAW file registry + ODS for Walmart inbound, carrier track and
Lingxing logistics channels (PRP ``PRPs/pmc-wfs-logistics-group.md`` §6.2 D-1 option A).

Frozen explicit DDL on a local MetaData with the project naming convention (same approach as
0071); ``tests/modules/pmc_wfs/test_source_files.py::test_migration_0076_matches_orm_metadata``
compares it with ``app.modules.pmc_wfs.source_models``. No data load, no backfill, no
permission grant. Downgrade refuses once any row exists so evidence is kept.
"""

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261103_0076_wfs_source_files"
down_revision = "20261102_0075_merge_wfs_skill_lib"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
TABLES = (
    "raw_pmc_wfs_source_files",
    "ods_walmart_wfs_inbound_shipments",
    "ods_walmart_wfs_inbound_items",
    "ods_walmart_wfs_receipts",
    "ods_carrier_zhongyi_orders",
    "ods_carrier_zhongyi_tracks",
    "ods_lingxing_logistics_channels",
)
J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _file_fk() -> sa.Column:
    return sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("raw_pmc_wfs_source_files.id", ondelete="RESTRICT"),
        nullable=False,
    )


def _tables(metadata: sa.MetaData) -> list[sa.Table]:
    tz = sa.DateTime(timezone=True)
    files = sa.Table(
        "raw_pmc_wfs_source_files",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("batch_label", sa.String(64), nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("loaded_rows", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("loaded_by", sa.String(128), nullable=False),
        sa.Column("loaded_at", tz, nullable=False),
        sa.CheckConstraint(
            "source IN ('walmart', 'zhongyi', 'lingxing')", name="pmc_wfs_source_file_source"
        ),
        sa.UniqueConstraint("source", "endpoint", "scope_key", "sha256"),
        sa.Index(
            "uq_pmc_wfs_source_file_current",
            "source",
            "endpoint",
            "scope_key",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )
    shipments = sa.Table(
        "ods_walmart_wfs_inbound_shipments",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("shipment_id", sa.String(64), nullable=False),
        sa.Column("inbound_order_id", sa.String(128)),
        sa.Column("status", sa.String(64)),
        sa.Column("created_date", sa.Date()),
        sa.Column("actual_delivery_date", sa.Date()),
        sa.Column("expected_delivery_date", sa.Date()),
        sa.Column("shipment_units", sa.Integer()),
        sa.Column("received_units", sa.Integer()),
        sa.Column("payload_json", J, nullable=False),
        sa.UniqueConstraint("file_id", "shipment_id"),
        sa.Index("ix_wm_wfs_ship_shipment", "shipment_id"),
    )
    items = sa.Table(
        "ods_walmart_wfs_inbound_items",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("shipment_id", sa.String(64), nullable=False),
        sa.Column("gtin", sa.String(64)),
        sa.Column("sku", sa.String(255)),
        sa.Column("item_qty", sa.Integer()),
        sa.Column("received_qty", sa.Integer()),
        sa.Column("damaged_qty", sa.Integer()),
        sa.Column("payload_json", J, nullable=False),
        sa.Index("ix_wm_wfs_item_shipment", "shipment_id", "gtin"),
    )
    receipts = sa.Table(
        "ods_walmart_wfs_receipts",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("shipment_id", sa.String(64), nullable=False),
        sa.Column("gtin", sa.String(64)),
        sa.Column("transaction_time", sa.String(40)),
        sa.Column("transaction_date", sa.Date()),
        sa.Column("changed_units", sa.Integer()),
        sa.Column("payload_json", J, nullable=False),
        sa.Index("ix_wm_wfs_receipt_shipment", "shipment_id", "gtin"),
    )
    orders = sa.Table(
        "ods_carrier_zhongyi_orders",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(64), nullable=False),
        sa.Column("customer_number", sa.String(128)),
        sa.Column("status", sa.String(64)),
        sa.Column("total_weight_kg", sa.String(32)),
        sa.Column("payload_json", J, nullable=False),
        sa.UniqueConstraint("file_id", "order_number"),
        sa.Index("ix_zy_order_customer", "customer_number"),
    )
    tracks = sa.Table(
        "ods_carrier_zhongyi_tracks",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(64), nullable=False),
        sa.Column("track_time", sa.String(40)),
        sa.Column("name", sa.Text()),
        sa.Column("payload_json", J, nullable=False),
        sa.Index("ix_zy_track_order", "order_number", "track_time"),
    )
    channels = sa.Table(
        "ods_lingxing_logistics_channels",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        _file_fk(),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("channel_name", sa.String(255)),
        sa.Column("provider_id", sa.String(64)),
        sa.Column("provider_name", sa.String(255)),
        sa.Column("method_name", sa.String(128)),
        sa.Column("enabled", sa.String(16)),
        sa.Column("payload_json", J, nullable=False),
        sa.UniqueConstraint("file_id", "channel_id"),
    )
    return [files, shipments, items, receipts, orders, tracks, channels]


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    for table in _tables(metadata):
        table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        count = bind.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        if count:
            raise RuntimeError(
                f"{table} has {count} rows; retain WFS source evidence, use forward recovery"
            )
    for table in reversed(TABLES):
        op.drop_table(table)
