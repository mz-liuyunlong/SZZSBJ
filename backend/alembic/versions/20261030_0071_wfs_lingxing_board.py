"""WFS shipment board fed from Lingxing: three append-only ODS tables, one published MART.

Frozen explicit DDL (282-03): table definitions are written out here on a local MetaData with
the project naming convention instead of importing ``app.modules.pmc_wfs.lingxing_models``,
so a later model change can never alter what this historical revision creates. The result is
identical to what the models emitted when this revision was first applied (same columns,
types, nullability, PK / unique / FK / check / index names);
``tests/modules/pmc_wfs/test_shipment_board.py::test_migration_0071_matches_orm_metadata``
compares the two. No data collection, no backfill, no permission grant. Downgrade refuses
once any row exists so evidence is kept.
"""

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0071_wfs_lingxing_board"
down_revision = "20261030_0070_merge_wfs_walmart_remote"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
# Creation order (parents first); downgrade drops in reverse.
TABLES = (
    "ods_lingxing_wfs_cargos",
    "ods_lingxing_wfs_cargo_goods",
    "ods_lingxing_wfs_shipping_lists",
    "gov_wfs_board_publications",
    "mart_wfs_shipment_board",
)
J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
PROVIDER_ID = 64
PROVIDER_TIME = 32


def _ods_columns() -> list:
    """Columns of the ODS mixin, in the order the models emitted them."""
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_request_ref_id",
            sa.Uuid(),
            sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_item_ordinal", sa.Integer(), nullable=False),
        sa.Column("payload_json", J, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _tables(metadata: sa.MetaData) -> list[sa.Table]:
    # Referenced integration tables (already migrated); declared only so FK names resolve.
    sa.Table("gov_integration_sync_runs", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    sa.Table("ods_api_raw_request_refs", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    tz = sa.DateTime(timezone=True)
    cargos = sa.Table(
        "ods_lingxing_wfs_cargos",
        metadata,
        *_ods_columns(),
        sa.Column("cargo_id", sa.String(PROVIDER_ID), nullable=False),
        sa.Column("cargo_code", sa.String(PROVIDER_ID)),
        sa.Column("in_bound_order_id", sa.String(128)),
        sa.Column("store_id", sa.String(PROVIDER_ID)),
        sa.Column("store_name", sa.String(255)),
        sa.Column("country_name", sa.String(64)),
        sa.Column("creator", sa.String(128)),
        sa.Column("logistics_code", sa.String(PROVIDER_ID)),
        sa.Column("cargo_create_date", sa.String(PROVIDER_TIME)),
        sa.Column("update_date", sa.String(PROVIDER_TIME)),
        sa.Column("system_update_date", sa.String(PROVIDER_TIME)),
        sa.Column("status", sa.Integer()),
        sa.Column("cargo_status", sa.String(64)),
        sa.Column("status_name", sa.String(64)),
        sa.Column("cargo_sync_status", sa.String(64)),
        sa.Column("shipping_list_codes", J, nullable=False),
        sa.Column("distribution_addresses", sa.Text()),
        sa.Column("return_addresses", sa.Text()),
        sa.Column("to_pending_at", tz),
        sa.Column("to_await_at", tz),
        sa.Column("to_receive_at", tz),
        sa.Column("to_closed_at", tz),
        sa.Column("to_cancelled_at", tz),
        sa.Column("goods_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        sa.UniqueConstraint("run_id", "source_account_ref", "cargo_id"),
        sa.Index("ix_wfs_cargos_code", "source_account_ref", "cargo_code"),
        sa.Index("ix_wfs_cargos_run", "run_id"),
    )
    goods = sa.Table(
        "ods_lingxing_wfs_cargo_goods",
        metadata,
        *_ods_columns(),
        sa.Column("cargo_id", sa.String(PROVIDER_ID), nullable=False),
        sa.Column("cargo_code", sa.String(PROVIDER_ID)),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("msku", sa.String(255)),
        sa.Column("sku", sa.String(255)),
        sa.Column("product_name", sa.String(500)),
        sa.Column("gtin", sa.String(64)),
        sa.Column("declare_num", sa.Integer()),
        sa.Column("shipments_num", sa.Integer()),
        sa.Column("received_num", sa.Integer()),
        sa.Column("damaged_qty", sa.Integer()),
        sa.UniqueConstraint("run_id", "source_account_ref", "cargo_id", "line_ordinal"),
        sa.Index("ix_wfs_cargo_goods_cargo", "run_id", "cargo_id"),
    )
    shipping = sa.Table(
        "ods_lingxing_wfs_shipping_lists",
        metadata,
        *_ods_columns(),
        sa.Column("shipping_code", sa.String(PROVIDER_ID), nullable=False),
        sa.Column("shipping_status", sa.String(32)),
        sa.Column("warehouse_id", sa.String(PROVIDER_ID)),
        sa.Column("logistics_provider_id", sa.String(PROVIDER_ID)),
        sa.Column("logistics_channel_id", sa.String(PROVIDER_ID)),
        sa.Column("logistics_code", sa.String(PROVIDER_ID)),
        sa.Column("creator", sa.String(128)),
        sa.Column("principal_user_name", sa.String(128)),
        sa.Column("gmt_create", sa.String(PROVIDER_TIME)),
        sa.Column("delivery_time", sa.String(PROVIDER_TIME)),
        sa.Column("actual_delivery_time", sa.String(PROVIDER_TIME)),
        sa.Column("sail_time", sa.String(PROVIDER_TIME)),
        sa.Column("arrival_time", sa.String(PROVIDER_TIME)),
        sa.Column("expected_arrival_time", sa.String(PROVIDER_TIME)),
        sa.Column("actual_due_time", sa.String(PROVIDER_TIME)),
        sa.Column("order_logistics_status", sa.String(64)),
        sa.Column("head_fee_type", sa.String(64)),
        sa.Column("shipping_remark", sa.Text()),
        sa.Column("cargo_codes", J, nullable=False),
        sa.Column("logistics_numbers", J, nullable=False),
        sa.Column("tracking_numbers", J, nullable=False),
        sa.Column("goods_count", sa.Integer(), nullable=False),
        sa.Column("box_num_total", sa.Integer()),
        sa.Column("shipments_num_total", sa.Integer()),
        sa.UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        sa.UniqueConstraint("run_id", "source_account_ref", "shipping_code"),
        sa.Index("ix_wfs_shipping_lists_run", "run_id"),
    )
    publications = sa.Table(
        "gov_wfs_board_publications",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("cargo_run_id", sa.Uuid(), nullable=False),
        sa.Column("shipping_run_id", sa.Uuid()),
        sa.Column("coverage_start", sa.Date(), nullable=False),
        sa.Column("coverage_end", sa.Date(), nullable=False),
        sa.Column("source_observed_at", tz, nullable=False),
        sa.Column("published_at", tz, nullable=False),
        sa.Column("builder_version", sa.String(64), nullable=False),
        sa.Column("quality_report", J, nullable=False),
        sa.CheckConstraint("status IN ('published')", name="wfs_board_publication_status"),
        sa.Index(
            "uq_wfs_board_current",
            "source_account_ref",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )
    board = sa.Table(
        "mart_wfs_shipment_board",
        metadata,
        sa.Column(
            "publication_id",
            sa.Uuid(),
            sa.ForeignKey("gov_wfs_board_publications.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("cargo_id", sa.String(PROVIDER_ID), nullable=False),
        sa.Column("cargo_code", sa.String(PROVIDER_ID)),
        sa.Column("in_bound_order_id", sa.String(128)),
        sa.Column("store_id", sa.String(PROVIDER_ID)),
        sa.Column("store_name", sa.String(255)),
        sa.Column("status", sa.Integer()),
        sa.Column("status_name", sa.String(64)),
        sa.Column("cargo_sync_status", sa.String(64)),
        sa.Column("logistics_code", sa.String(PROVIDER_ID)),
        sa.Column("cargo_created_at", tz),
        sa.Column("cargo_updated_at", tz),
        sa.Column("to_await_at", tz),
        sa.Column("to_receive_at", tz),
        sa.Column("to_closed_at", tz),
        sa.Column("to_cancelled_at", tz),
        sa.Column("declared_units", sa.Integer()),
        sa.Column("shipped_units", sa.Integer()),
        sa.Column("received_units", sa.Integer()),
        sa.Column("damaged_units", sa.Integer()),
        sa.Column("sku_count", sa.Integer(), nullable=False),
        sa.Column("shipping_codes", J, nullable=False),
        sa.Column("shipping_status", sa.String(32)),
        sa.Column("warehouse_id", sa.String(PROVIDER_ID)),
        sa.Column("actual_delivery_date", sa.Date()),
        sa.Column("arrival_date", sa.Date()),
        sa.Column("expected_arrival_date", sa.Date()),
        sa.Column("logistics_numbers", J, nullable=False),
        sa.Column("payload_json", J, nullable=False),
        sa.UniqueConstraint("publication_id", "source_account_ref", "cargo_id"),
        sa.Index("ix_wfs_board_status", "publication_id", "status", "cargo_created_at"),
        sa.Index("ix_wfs_board_store", "publication_id", "store_id"),
        sa.Index("ix_wfs_board_code", "publication_id", "cargo_code"),
        sa.Index("ix_wfs_board_inbound", "publication_id", "in_bound_order_id"),
    )
    return [cargos, goods, shipping, publications, board]


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
                f"{table} has {count} rows; retain WFS evidence, use forward recovery"
            )
    for table in reversed(TABLES):
        op.drop_table(table)
