"""Local packing decisions and immutable events; provider snapshots remain read-only."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

J = JSON().with_variant(JSONB(), "postgresql")


def now():
    return datetime.now(UTC)


class PackingSequence(Base):
    __tablename__ = "ops_domestic_pk_sequences"
    __table_args__ = (CheckConstraint("last_value BETWEEN 1 AND 999", name="pk_daily_limit"),)
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class PackingOrder(Base):
    __tablename__ = "ops_domestic_packing_orders"
    __table_args__ = (
        Index(
            "ix_domestic_packing_orders_scope",
            "source_account_ref",
            "warehouse_id",
            text("created_at DESC"),
            "id",
        ),
        CheckConstraint("is_test", name="packing_local_verification"),
        CheckConstraint("status<>'rejected' OR length(trim(note))>0", name="packing_reject_note"),
        UniqueConstraint("source_account_ref", "candidate_id"),
        ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('approved','rejected')", name="packing_status"),
        CheckConstraint("version > 0", name="packing_version"),
        CheckConstraint(
            "(status='approved' AND pk IS NOT NULL AND qty BETWEEN 1 AND 1000000) "
            "OR (status='rejected' AND pk IS NULL AND qty IS NULL)",
            name="packing_decision_fields",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(nullable=False)
    inbound_order_sn: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(255), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(String(64))
    pk: Mapped[str | None] = mapped_column(String(32), unique=True)
    qty: Mapped[int | None] = mapped_column(Integer)
    customs_value: Mapped[bool | None] = mapped_column(Boolean)
    customs_src: Mapped[str] = mapped_column(String(16), nullable=False)
    rwh: Mapped[str | None] = mapped_column(String(128))
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_publication_id: Mapped[UUID] = mapped_column(nullable=False)
    source_board_id: Mapped[UUID] = mapped_column(nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(J, nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )


class PackingAllocation(Base):
    __tablename__ = "ops_domestic_packing_allocations"
    __table_args__ = (
        Index(
            "ix_domestic_packing_allocation_source",
            "source_account_ref",
            "warehouse_id",
            "source_board_id",
        ),
        ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("qty > 0", name="packing_allocation_positive"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_board_id: Mapped[UUID] = mapped_column(nullable=False)
    source_publication_id: Mapped[UUID] = mapped_column(nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)


class PackingEvent(Base):
    __tablename__ = "evt_domestic_packing_events"
    __table_args__ = (
        CheckConstraint("order_version>0", name="packing_event_version"),
        UniqueConstraint("source_account_ref", "idempotency_key"),
        UniqueConstraint("order_id", "order_version"),
        CheckConstraint("event_kind IN ('approve','reject')", name="packing_event_kind"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(J, nullable=False)
    response_json: Mapped[dict] = mapped_column(J, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )
