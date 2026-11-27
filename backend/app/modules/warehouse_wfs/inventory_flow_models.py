"""Lingxing WFS cost-valuation flow ODS (inventory claim PRP, PR 1).

One table per provider interface: ``LX-8437AD0BCB9E`` lands here only. The settlement
profit V2 module reads rows with ``is_current = true`` and never writes this table.

Identity is the provider page plus the row position on that page. ``serial_number`` is
kept for tracing only: provider serial numbers repeat inside one pull and are reassigned
between pulls, so no business column is unique.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

WFS_COST_VALUATION_FLOW_TABLE: Final = "ods_lingxing_wfs_cost_valuation_flow"
STORE_MAPPING_STATUSES: Final = ("mapped", "unmapped")
MONEY = Numeric(18, 4)


def utc_now() -> datetime:
    return datetime.now(UTC)


class WfsCostValuationFlowOds(Base):
    __tablename__ = WFS_COST_VALUATION_FLOW_TABLE
    __table_args__ = (
        UniqueConstraint(
            "raw_request_ref_id",
            "source_item_ordinal",
            name="uq_wfs_cost_flow_request_ordinal",
        ),
        CheckConstraint("source_item_ordinal >= 0", name="wfs_cost_flow_ordinal_nonnegative"),
        CheckConstraint("window_end >= window_start", name="wfs_cost_flow_window_order"),
        CheckConstraint(
            "store_mapping_status IN ('mapped', 'unmapped')",
            name="wfs_cost_flow_store_mapping_status",
        ),
        CheckConstraint(
            "(store_mapping_status = 'mapped') = (store_id IS NOT NULL)",
            name="wfs_cost_flow_store_mapping_consistent",
        ),
        CheckConstraint(
            "currency_code IS NULL OR length(currency_code) = 3",
            name="wfs_cost_flow_currency_code",
        ),
        CheckConstraint(
            "NOT is_current OR superseded_by_run_id IS NULL",
            name="wfs_cost_flow_current_not_superseded",
        ),
        Index(
            "ix_wfs_cost_flow_current_type_date",
            "source_account_ref",
            "is_current",
            "business_type",
            "business_date",
        ),
        Index(
            "ix_wfs_cost_flow_current_store_msku",
            "source_account_ref",
            "store_code",
            "msku",
            postgresql_where=text("is_current"),
        ),
        Index(
            "ix_wfs_cost_flow_current_settlement",
            "source_account_ref",
            "settlement_date",
            postgresql_where=text("is_current"),
        ),
        Index("ix_wfs_cost_flow_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "gov_integration_sync_runs.id", ondelete="RESTRICT", name="fk_wfs_cost_flow_run"
        ),
        nullable=False,
    )
    raw_request_ref_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "ods_api_raw_request_refs.id", ondelete="RESTRICT", name="fk_wfs_cost_flow_raw_ref"
        ),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_item_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    superseded_by_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "gov_integration_sync_runs.id",
            ondelete="RESTRICT",
            name="fk_wfs_cost_flow_superseded_run",
        )
    )

    serial_number: Mapped[str | None] = mapped_column(String(32))
    date_local: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[date | None] = mapped_column(Date)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    store_mapping_status: Mapped[str] = mapped_column(String(16), nullable=False)
    msku: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    business_name: Mapped[str | None] = mapped_column(Text)
    business_desc: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    business_number: Mapped[str | None] = mapped_column(Text)
    order_number: Mapped[str | None] = mapped_column(Text)
    cost_source: Mapped[str | None] = mapped_column(Text)
    order_base_purchase_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    purchase_total_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    order_base_logistics_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    logistics_total_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    order_base_other_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    other_total_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
