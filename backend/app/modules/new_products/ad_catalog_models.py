"""Walmart advertising read models, not a second spend ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WalmartAdItemHistory(Base):
    __tablename__ = "biz_walmart_ad_item_history"
    __table_args__ = (
        Index("ix_wad_hist_item_seen", "item_id", "source_observed_at"),
        Index("ix_wad_hist_campaign", "advertiser_id", "campaign_id"),
    )

    source_blob_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    advertiser_id: Mapped[str | None] = mapped_column(String(128))
    campaign_id: Mapped[str | None] = mapped_column(String(128))
    ad_group_id: Mapped[str | None] = mapped_column(String(128))
    ad_item_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    campaign_and_targeting_type: Mapped[str | None] = mapped_column(String(128))
    campaign_kind: Mapped[str | None] = mapped_column(String(16))
    entity_created_at_raw: Mapped[str | None] = mapped_column(Text)
    add_date_raw: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WalmartAdCampaignCatalog(Base):
    __tablename__ = "biz_walmart_ad_campaign_catalog"
    __table_args__ = (Index("ix_wad_campaign_kind", "campaign_kind"),)

    advertiser_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_and_targeting_type: Mapped[str | None] = mapped_column(String(128))
    campaign_kind: Mapped[str | None] = mapped_column(String(16))
    classification_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    campaign_name: Mapped[str | None] = mapped_column(Text)
    campaign_status: Mapped[str | None] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_blob_id: Mapped[UUID] = mapped_column(nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WalmartAdItemCurrent(Base):
    __tablename__ = "biz_walmart_ad_item_current"
    __table_args__ = (Index("ix_wad_item_current_item", "item_id"),)

    advertiser_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ad_group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ad_item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_kind: Mapped[str | None] = mapped_column(String(16))
    ad_group_name: Mapped[str | None] = mapped_column(Text)
    ad_group_status: Mapped[str | None] = mapped_column(String(128))
    ad_status: Mapped[str | None] = mapped_column(String(128))
    entity_created_at_raw: Mapped[str | None] = mapped_column(Text)
    add_date_raw: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_blob_id: Mapped[UUID] = mapped_column(nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WalmartAdIngestCursor(Base):
    __tablename__ = "biz_walmart_ad_ingest_cursor"

    source_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_blob_id: Mapped[UUID | None] = mapped_column()
    processed_blobs: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    processed_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
