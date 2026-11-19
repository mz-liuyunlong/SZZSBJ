"""Walmart advertisement item catalog and lossless historical snapshots.

Revision ID: 20261120_0094_walmart_ad_catalog
Revises: 20261119_0093_np_market_competitors

Existing FACT spend remains authoritative. No backfill or data mutation in DDL.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261120_0094_walmart_ad_catalog"
down_revision = "20261119_0093_np_market_competitors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ad_raw_cursor", "ods_api_raw_blobs",
        ["retention_policy_id", "received_at", "id"],
        postgresql_where=sa.text("storage_mode = 'database' AND payload_json IS NOT NULL"),
    )
    op.create_table(
        "biz_walmart_ad_item_history",
        sa.Column("source_blob_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_ordinal", sa.Integer(), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("advertiser_id", sa.String(128)),
        sa.Column("campaign_id", sa.String(128)),
        sa.Column("ad_group_id", sa.String(128)),
        sa.Column("ad_item_id", sa.String(128)),
        sa.Column("item_id", sa.String(128)),
        sa.Column("campaign_and_targeting_type", sa.String(128)),
        sa.Column("campaign_kind", sa.String(16)),
        sa.Column("entity_created_at_raw", sa.Text()),
        sa.Column("add_date_raw", sa.Text()),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("source_blob_id", "source_ordinal", name="pk_wad_item_history"),
    )
    op.create_index(
        "ix_wad_hist_item_seen", "biz_walmart_ad_item_history",
        ["item_id", "source_observed_at"],
    )
    op.create_index(
        "ix_wad_hist_campaign", "biz_walmart_ad_item_history",
        ["advertiser_id", "campaign_id"],
    )
    op.create_table(
        "biz_walmart_ad_campaign_catalog",
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("campaign_id", sa.String(128), nullable=False),
        sa.Column("campaign_and_targeting_type", sa.String(128)),
        sa.Column("campaign_kind", sa.String(16)),
        sa.Column("classification_conflict", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("campaign_name", sa.Text()),
        sa.Column("campaign_status", sa.String(128)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_blob_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("advertiser_id", "campaign_id", name="pk_wad_campaign_catalog"),
    )
    op.create_index(
        "ix_wad_campaign_kind", "biz_walmart_ad_campaign_catalog", ["campaign_kind"]
    )
    op.create_table(
        "biz_walmart_ad_item_current",
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("campaign_id", sa.String(128), nullable=False),
        sa.Column("ad_group_id", sa.String(128), nullable=False),
        sa.Column("ad_item_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("campaign_kind", sa.String(16)),
        sa.Column("ad_group_name", sa.Text()),
        sa.Column("ad_group_status", sa.String(128)),
        sa.Column("ad_status", sa.String(128)),
        sa.Column("entity_created_at_raw", sa.Text()),
        sa.Column("add_date_raw", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_blob_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "advertiser_id", "campaign_id", "ad_group_id", "ad_item_id", "item_id",
            name="pk_wad_item_current",
        ),
    )
    op.create_index(
        "ix_wad_item_current_item", "biz_walmart_ad_item_current", ["item_id"]
    )
    op.create_table(
        "biz_walmart_ad_ingest_cursor",
        sa.Column("source_key", sa.String(128), primary_key=True),
        sa.Column("last_received_at", sa.DateTime(timezone=True)),
        sa.Column("last_blob_id", UUID(as_uuid=True)),
        sa.Column("processed_blobs", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("biz_walmart_ad_ingest_cursor")
    op.drop_index("ix_wad_item_current_item", table_name="biz_walmart_ad_item_current")
    op.drop_table("biz_walmart_ad_item_current")
    op.drop_index("ix_wad_campaign_kind", table_name="biz_walmart_ad_campaign_catalog")
    op.drop_table("biz_walmart_ad_campaign_catalog")
    op.drop_index("ix_wad_hist_campaign", table_name="biz_walmart_ad_item_history")
    op.drop_index("ix_wad_hist_item_seen", table_name="biz_walmart_ad_item_history")
    op.drop_table("biz_walmart_ad_item_history")
    op.drop_index("ix_ad_raw_cursor", table_name="ods_api_raw_blobs")
