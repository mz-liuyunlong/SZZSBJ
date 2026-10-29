"""Draft snapshots and exclusive physical box-line holds, separate from stock allocation."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import J, now


class WfsDraft(Base):
    __tablename__ = "ops_pmc_wfs_drafts"
    __table_args__ = (CheckConstraint("status = 'pending'", name="wfs_pending_only"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), index=True)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    business_test: Mapped[bool]
    payload: Mapped[dict] = mapped_column(J, nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WfsDraftItem(Base):
    __tablename__ = "ops_pmc_wfs_draft_items"
    __table_args__ = (CheckConstraint("boxes>0 AND units_per_box>0", name="wfs_item_quantity"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("ops_pmc_wfs_drafts.id"), index=True)
    sku: Mapped[str] = mapped_column(String(255))
    gtin: Mapped[str] = mapped_column(String(14))
    boxes: Mapped[int] = mapped_column(Integer)
    units_per_box: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(J)


class WfsBoxAllocation(Base):
    __tablename__ = "ops_pmc_wfs_box_allocations"
    __table_args__ = (
        UniqueConstraint("box_line_id"),
        Index("ix_wfs_alloc_order", "order_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("ops_pmc_wfs_draft_items.id"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("ops_domestic_packing_orders.id"))
    box_line_id: Mapped[UUID] = mapped_column(ForeignKey("ops_domestic_packing_box_lines.id"))
    box_version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(J)


class WfsEvent(Base):
    __tablename__ = "evt_pmc_wfs_draft_events"
    __table_args__ = (UniqueConstraint("source_account_ref", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(32))
    actor_uid: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    request_json: Mapped[dict] = mapped_column(J)
    response_json: Mapped[dict] = mapped_column(J)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
