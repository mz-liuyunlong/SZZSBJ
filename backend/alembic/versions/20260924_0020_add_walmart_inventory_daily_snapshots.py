from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260924_0020_walmart_inventory_daily"
down_revision: str | None = "20260923_0019_after_sales_reason_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_walmart_listing_inventory_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("snapshot_date_la", sa.Date(), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column(
            "available_quantity",
            sa.Numeric(18, 4),
            nullable=True,
        ),
        sa.Column(
            "wfs_available_quantity",
            sa.Numeric(18, 4),
            nullable=True,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "available_quantity IS NULL OR available_quantity >= 0",
            name="ck_fact_walmart_inventory_daily_available_nonnegative",
        ),
        sa.CheckConstraint(
            "wfs_available_quantity IS NULL OR wfs_available_quantity >= 0",
            name="ck_fact_walmart_inventory_daily_wfs_nonnegative",
        ),
        sa.UniqueConstraint(
            "snapshot_date_la",
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_fact_walmart_inventory_daily_identity",
        ),
    )

    op.create_index(
        "ix_fact_walmart_inventory_daily_account_date",
        "fact_walmart_listing_inventory_daily",
        ["source_account_ref", "snapshot_date_la"],
    )

    op.create_index(
        "ix_fact_walmart_inventory_daily_item_date",
        "fact_walmart_listing_inventory_daily",
        ["source_account_ref", "store_id", "item_id", "snapshot_date_la"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fact_walmart_inventory_daily_item_date",
        table_name="fact_walmart_listing_inventory_daily",
    )
    op.drop_index(
        "ix_fact_walmart_inventory_daily_account_date",
        table_name="fact_walmart_listing_inventory_daily",
    )
    op.drop_table("fact_walmart_listing_inventory_daily")
