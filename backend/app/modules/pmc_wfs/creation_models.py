"""V2 durable operations; historical pending drafts are never rewritten."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import J, now


class WfsCreation(Base):
    __tablename__ = "ops_wfs_creation_operations"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "idempotency_key"),
        CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN','PARTIAL')",
            name="wfs_creation_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"), index=True
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), index=True)
    store_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(J)
    actor_uid: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="QUEUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WfsCreationTicket(Base):
    __tablename__ = "ops_wfs_creation_tickets"
    __table_args__ = (
        UniqueConstraint("operation_id", "number"),
        CheckConstraint("number > 0", name="wfs_ticket_number"),
        CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN')", name="wfs_ticket_state"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_wfs_creation_operations.id", ondelete="RESTRICT"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="QUEUED")
    allocation: Mapped[dict] = mapped_column(J)
    result: Mapped[dict] = mapped_column(J, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))


class WfsBoxHold(Base):
    __tablename__ = "ops_wfs_box_holds"
    __table_args__ = (
        UniqueConstraint("box_line_id", "box_version", "box_ordinal"),
        CheckConstraint("box_version > 0 AND box_ordinal > 0", name="wfs_hold_positive"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_wfs_creation_tickets.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"), index=True
    )
    box_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_box_lines.id", ondelete="RESTRICT"), index=True
    )
    box_version: Mapped[int] = mapped_column(Integer)
    box_ordinal: Mapped[int] = mapped_column(Integer)


class WfsCreationEvent(Base):
    __tablename__ = "evt_wfs_creation_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_wfs_creation_operations.id", ondelete="RESTRICT"), index=True
    )
    actor_uid: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[dict] = mapped_column(J)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
