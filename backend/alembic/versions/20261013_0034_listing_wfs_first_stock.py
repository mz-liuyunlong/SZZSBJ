"""record first observed WFS stock on newly monitored listings

Revision ID: 20261013_0034_listing_wfs_first_stock
Revises: 20261010_0033_add_wfs_low_price_surcharge
Create Date: 2026-10-13

This migration creates an EMPTY tracking table. No existing listings are
backfilled. Existing current-state records remain excluded by the writer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0034_listing_wfs_first_stock"
down_revision: str | None = "20261010_0033_add_wfs_low_price_surcharge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_wfs_first_stock",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("monitoring_started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_wfs_seen_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("launch_date_cn", sa.Date(), nullable=True),
        sa.Column("date_source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(msku) <> ''", name="ck_listing_wfs_first_stock_msku"),
        sa.CheckConstraint("btrim(store_id) <> ''", name="ck_listing_wfs_first_stock_store"),
        sa.CheckConstraint("btrim(item_id) <> ''", name="ck_listing_wfs_first_stock_item"),
        sa.CheckConstraint(
            "date_source in ('pending','wfs_first_stock','legacy_verified')",
            name="ck_listing_wfs_first_stock_source",
        ),
        sa.CheckConstraint(
            "(launch_date_cn IS NULL AND first_wfs_seen_at_utc IS NULL) OR "
            "(launch_date_cn IS NOT NULL AND "
            "(first_wfs_seen_at_utc IS NOT NULL OR "
            "date_source = 'legacy_verified'))",
            name="ck_listing_wfs_first_stock_date_pair",
        ),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            "msku",
            name="uq_listing_wfs_first_stock_identity",
        ),
    )
    op.create_index(
        "ix_listing_wfs_first_stock_store_item",
        "listing_wfs_first_stock",
        ["source_account_ref", "store_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_wfs_first_stock_store_item", table_name="listing_wfs_first_stock")
    op.drop_table("listing_wfs_first_stock")
