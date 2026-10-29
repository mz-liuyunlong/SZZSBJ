"""Four run-scoped Walmart business tables and an atomic ingestion receipt."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261029_0069_walmart_remote_business"
down_revision = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None

TABLES = (
    "walmart_remote_wfs_inventory",
    "walmart_remote_inbound_shipments",
    "walmart_remote_inbound_items",
    "walmart_remote_inventory_log",
)


def upgrade() -> None:
    op.create_table(
        "walmart_remote_ingest_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("walmart_remote_jobs.id"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_code", sa.String(16), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("file_hashes", postgresql.JSONB(), nullable=False),
        sa.Column("row_counts", postgresql.JSONB(), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("store_id", "run_id", name="uq_walmart_remote_ingest_run"),
    )
    for table in TABLES:
        op.create_table(
            table,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("source_account_ref", sa.String(128), nullable=False),
            sa.Column("store_id", sa.String(128), nullable=False),
            sa.Column("run_id", sa.String(80), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.String(128)),
            sa.Column("sku", sa.String(255)),
            sa.Column("gtin", sa.String(128)),
            sa.Column("shipment_id", sa.String(128)),
            sa.Column("event_id", sa.String(128)),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint("store_id", "run_id", "row_number", name="uq_" + table + "_row"),
        )
        op.create_index(
            "ix_" + table + "_store_date",
            table,
            ["source_account_ref", "store_id", "snapshot_date"],
        )
        op.create_index(
            "ix_" + table + "_identity", table, ["store_id", "item_id", "sku"]
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index("ix_" + table + "_identity", table_name=table)
        op.drop_index("ix_" + table + "_store_date", table_name=table)
        op.drop_table(table)
    op.drop_table("walmart_remote_ingest_batches")
