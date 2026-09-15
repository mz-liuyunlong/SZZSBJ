from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class MediaImageAsset(Base):
    """Deduplicated cached image asset derived from one external source URL."""

    __tablename__ = "media_image_assets"
    __table_args__ = (
        UniqueConstraint("source_url_hash"),
        CheckConstraint("char_length(source_url_hash) = 64", name="source_url_hash_sha256"),
        CheckConstraint(
            "content_hash IS NULL OR char_length(content_hash) = 64",
            name="content_hash_sha256",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="status",
        ),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint(
            "source_bytes IS NULL OR source_bytes >= 0",
            name="source_bytes_nonnegative",
        ),
        CheckConstraint(
            "source_width IS NULL OR source_width > 0",
            name="source_width_positive",
        ),
        CheckConstraint(
            "source_height IS NULL OR source_height > 0",
            name="source_height_positive",
        ),
        Index("ix_media_image_assets_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_host: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    content_hash: Mapped[str | None] = mapped_column(String(64))
    mime_type: Mapped[str | None] = mapped_column(String(64))
    source_width: Mapped[int | None] = mapped_column(Integer)
    source_height: Mapped[int | None] = mapped_column(Integer)
    source_bytes: Mapped[int | None] = mapped_column(Integer)
    thumbnail_128_key: Mapped[str | None] = mapped_column(Text)
    preview_512_key: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class MediaImageSourceLink(Base):
    """Links immutable source-image rows to a deduplicated cached asset."""

    __tablename__ = "media_image_source_links"
    __table_args__ = (
        UniqueConstraint("source_image_id"),
        Index("ix_media_image_source_links_asset_id", "asset_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_image_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_images.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_image_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
