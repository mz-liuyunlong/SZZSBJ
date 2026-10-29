"""Durable WFS fulfillment exception cases; detection rules arrive in a later slice."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import J, now


class WfsExceptionCase(Base):
    __tablename__ = "ops_wfs_exception_cases"
    __table_args__ = (
        UniqueConstraint("dedupe_key"),
        CheckConstraint("severity IN ('HIGH','MEDIUM','LOW')", name="wfs_exception_severity"),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','WAITING_EXTERNAL','RESOLVED','CLOSED')",
            name="wfs_exception_status",
        ),
        CheckConstraint("version >= 1", name="wfs_exception_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(512))
    source_account_ref: Mapped[str] = mapped_column(String(128), index=True)
    store_id: Mapped[str] = mapped_column(String(64), index=True)
    shipment_id: Mapped[str] = mapped_column(String(128), index=True)
    shipment_row_id: Mapped[str | None] = mapped_column(String(256))
    ticket_id: Mapped[UUID | None]
    rule_family: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    assignee_user_id: Mapped[str | None] = mapped_column(String(128))
    platform_case_ref: Mapped[str | None] = mapped_column(String(128))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_basis: Mapped[str | None] = mapped_column(Text)
    pk: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(64))
    gtin: Mapped[str | None] = mapped_column(String(32))
    msku: Mapped[str | None] = mapped_column(String(128))
    qty_variance: Mapped[int | None] = mapped_column(Integer)
    business_test: Mapped[bool] = mapped_column(default=False)
    evidence: Mapped[dict] = mapped_column(J, default=dict)
    rule_version: Mapped[str] = mapped_column(String(64), default="M1_STUB")
    version: Mapped[int] = mapped_column(Integer, default=1)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WfsExceptionDetection(Base):
    __tablename__ = "evt_wfs_exception_detections"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('HIT','MISS','CANNOT_JUDGE')",
            name="wfs_exception_detection_outcome",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_wfs_exception_cases.id", ondelete="RESTRICT"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(32))
    rule_version: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(J, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WfsExceptionAction(Base):
    __tablename__ = "evt_wfs_exception_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('ASSIGN','NOTE','RESOLVE','CLOSE','REOPEN','MARK_WAITING')",
            name="wfs_exception_action_type",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_wfs_exception_cases.id", ondelete="RESTRICT"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(32))
    actor_uid: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(J, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
