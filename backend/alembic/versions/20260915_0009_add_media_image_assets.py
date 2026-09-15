"""Add cached media image asset metadata.

Revision ID: 20260915_0009
Revises: 20260914_0008
Create Date: 2026-09-15

This migration creates metadata/link tables only. It does not download images,
backfill existing source rows, or touch external services.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260915_0009"
down_revision: str | Sequence[str] | None = "20260914_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_image_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_url_hash", sa.String(64), nullable=False),
        sa.Column("source_host", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("mime_type", sa.String(64), nullable=True),
        sa.Column("source_width", sa.Integer(), nullable=True),
        sa.Column("source_height", sa.Integer(), nullable=True),
        sa.Column("source_bytes", sa.Integer(), nullable=True),
        sa.Column("thumbnail_128_key", sa.Text(), nullable=True),
        sa.Column("preview_512_key", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(source_url_hash) = 64",
            name=op.f("ck_media_image_assets_source_url_hash_sha256"),
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR char_length(content_hash) = 64",
            name=op.f("ck_media_image_assets_content_hash_sha256"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name=op.f("ck_media_image_assets_status"),
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name=op.f("ck_media_image_assets_retry_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "source_bytes IS NULL OR source_bytes >= 0",
            name=op.f("ck_media_image_assets_source_bytes_nonnegative"),
        ),
        sa.CheckConstraint(
            "source_width IS NULL OR source_width > 0",
            name=op.f("ck_media_image_assets_source_width_positive"),
        ),
        sa.CheckConstraint(
            "source_height IS NULL OR source_height > 0",
            name=op.f("ck_media_image_assets_source_height_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_image_assets")),
        sa.UniqueConstraint(
            "source_url_hash",
            name=op.f("uq_media_image_assets_source_url_hash"),
        ),
    )
    op.create_index(
        "ix_media_image_assets_status_updated",
        "media_image_assets",
        ["status", "updated_at"],
    )

    op.create_table(
        "media_image_source_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["media_image_assets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_image_id"],
            ["dwd_lingxing_sku_product_images.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_image_source_links")),
        sa.UniqueConstraint(
            "source_image_id",
            name=op.f("uq_media_image_source_links_source_image_id"),
        ),
    )
    op.create_index(
        "ix_media_image_source_links_asset_id",
        "media_image_source_links",
        ["asset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_image_source_links_asset_id",
        table_name="media_image_source_links",
    )
    op.drop_table("media_image_source_links")
    op.drop_index(
        "ix_media_image_assets_status_updated",
        table_name="media_image_assets",
    )
    op.drop_table("media_image_assets")
