"""Versioned inbound read model; receipt DWD remains unchanged."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.models import DomesticOdsMixin

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class DomesticWarehouseStatement(DomesticOdsMixin, Base):
    __tablename__ = "ods_lingxing_domestic_warehouse_statements"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "statement_id"),
        Index(
            "ix_domestic_statement_ib",
            "source_account_ref",
            "source_warehouse_id",
            "order_sn",
            "sku",
        ),
    )
    statement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_sn: Mapped[str | None] = mapped_column(String(64))
    ref_order_sn: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[str | None] = mapped_column(String(64))
    sub_type: Mapped[str | None] = mapped_column(String(32))
    product_total: Mapped[int | None] = mapped_column(Integer)
    product_qc_num: Mapped[int | None] = mapped_column(Integer)
    product_good_num: Mapped[int | None] = mapped_column(Integer)
    product_bad_num: Mapped[int | None] = mapped_column(Integer)
    opt_time: Mapped[str | None] = mapped_column(String(32))


class DomesticBoardPublication(Base):
    __tablename__ = "gov_domestic_board_publications"
    __table_args__ = (
        CheckConstraint("status IN ('published')", name="publication_status"),
        Index(
            "uq_domestic_board_current",
            "source_account_ref",
            "source_warehouse_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="published", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    batch_run_id: Mapped[UUID] = mapped_column(nullable=False)
    statement_run_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    coverage_start: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end: Mapped[date] = mapped_column(Date, nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class DomesticInboundBoard(Base):
    __tablename__ = "mart_domestic_inbound_batch_board"
    __table_args__ = (
        Index("ix_domestic_inbound_date", "publication_id", "arrival_business_date", "id"),
        Index("ix_domestic_inbound_sku", "publication_id", "sku"),
        UniqueConstraint(
            "publication_id",
            "source_account_ref",
            "source_warehouse_id",
            "inbound_order_sn",
            "sku",
            "attribution_key",
        ),
    )
    publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_domestic_board_publications.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_order_sn: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(255), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(64))
    attribution_key: Mapped[str] = mapped_column(String(64), nullable=False)
    arrival_business_date: Mapped[date | None] = mapped_column(Date)
    balance_num: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
