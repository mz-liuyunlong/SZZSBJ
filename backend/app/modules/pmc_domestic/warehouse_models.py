"""Warehouse-owned projections; approvals, inventory and product masters remain separate."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import J, now


class PackingBoxSet(Base):
    __tablename__ = "ops_domestic_packing_box_sets"
    __table_args__ = (
        CheckConstraint("version>0", name="warehouse_box_version"),
        CheckConstraint("total_qty BETWEEN 1 AND 1000000", name="warehouse_box_total"),
        CheckConstraint(
            "approved_qty_snapshot BETWEEN 1 AND 1000000", name="warehouse_approved_qty"
        ),
        CheckConstraint(
            "(completed_at IS NULL AND completed_by IS NULL) OR "
            "(completed_at IS NOT NULL AND completed_by IS NOT NULL)",
            name="warehouse_completion",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_qty_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    variance_reason: Mapped[str | None] = mapped_column(String(500))
    package_snapshot: Mapped[dict | None] = mapped_column(J)
    product_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String(128))
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class PackingBoxLine(Base):
    __tablename__ = "ops_domestic_packing_box_lines"
    __table_args__ = (
        UniqueConstraint("box_set_id", "line_no"),
        CheckConstraint("line_no BETWEEN 1 AND 20", name="warehouse_line_no"),
        CheckConstraint("box_type IN ('A','B','C','custom')", name="warehouse_box_type"),
        CheckConstraint(
            "boxes BETWEEN 1 AND 9999 AND units_per_box BETWEEN 1 AND 100000",
            name="warehouse_line_quantity",
        ),
        CheckConstraint(
            "length_cm BETWEEN 1 AND 300 AND width_cm BETWEEN 1 AND 300 "
            "AND height_cm BETWEEN 1 AND 300",
            name="warehouse_box_dimensions",
        ),
        CheckConstraint("gross_weight_kg BETWEEN 0.01 AND 200", name="warehouse_box_weight"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    box_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_box_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    box_type: Mapped[str] = mapped_column(String(16), nullable=False)
    boxes: Mapped[int] = mapped_column(Integer, nullable=False)
    units_per_box: Mapped[int] = mapped_column(Integer, nullable=False)
    length_cm: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    width_cm: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)


class PackingWarehouseNote(Base):
    __tablename__ = "ops_domestic_packing_notes"
    __table_args__ = (
        CheckConstraint(
            "category IN ('arrival_incomplete','labels','materials','operations',"
            "'schedule','quality','other','resolved')",
            name="warehouse_note_category",
        ),
        CheckConstraint("category<>'other' OR length(trim(text))>=2", name="warehouse_note_text"),
        CheckConstraint("resolved=(category='resolved')", name="warehouse_note_resolution"),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("evt_domestic_packing_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class PackingVarianceCase(Base):
    """Current exception projection; every transition is captured by immutable PK events."""

    __tablename__ = "ops_domestic_packing_variance_cases"
    __table_args__ = (
        CheckConstraint("kind IN ('under','over')", name="packing_variance_kind"),
        CheckConstraint(
            "state IN ('pending','blocked','ready','released','voided','resolved')",
            name="packing_variance_state",
        ),
        CheckConstraint(
            "quantity>0 AND (gap_qty IS NULL OR gap_qty>=0)", name="packing_variance_qty"
        ),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_qty: Mapped[int | None] = mapped_column(Integer)
    reason_category: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(500))
    supplemental_ib: Mapped[str | None] = mapped_column(String(128))
    evidence: Mapped[dict] = mapped_column(J, nullable=False, default=dict)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class PackingNotificationOutbox(Base):
    """Local durable notification tasks. No delivery worker or external send is enabled."""

    __tablename__ = "ops_domestic_packing_notification_outbox"
    __table_args__ = (
        UniqueConstraint("order_id", "order_version", "kind"),
        CheckConstraint(
            "state IN ('pending_configuration','cancelled','delivered','failed')",
            name="packing_notice_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"), nullable=False
    )
    order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_configuration")
    payload: Mapped[dict] = mapped_column(J, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
