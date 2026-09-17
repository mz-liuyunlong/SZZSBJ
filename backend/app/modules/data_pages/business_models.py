from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class WalmartSampleOrderItemFact(Base):
    __tablename__ = "fact_walmart_sample_order_items"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "platform_order_no", "source_order_line_id"),
        CheckConstraint(
            "quantity IS NULL OR quantity >= 0",
            name="ck_sample_quantity_nonnegative",
        ),
        CheckConstraint(
            "unit_price_amount IS NULL OR unit_price_amount >= 0",
            name="ck_sample_unit_price_nonnegative",
        ),
        CheckConstraint(
            "order_total_amount IS NULL OR order_total_amount >= 0",
            name="ck_sample_order_total_nonnegative",
        ),
        Index(
            "ix_fact_walmart_sample_order_items_business_date",
            "business_date_utc_minus_7",
        ),
        Index(
            "ix_fact_walmart_sample_order_items_store_sku",
            "store_id",
            "local_sku",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_date_utc_minus_7: Mapped[date] = mapped_column(Date, nullable=False)
    business_timezone: Mapped[str] = mapped_column(
        String(64),
        default="UTC-07:00",
        server_default=text("'UTC-07:00'"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_order_id: Mapped[str | None] = mapped_column(String(128))
    platform_order_no: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    store_name: Mapped[str | None] = mapped_column(Text)
    platform_code: Mapped[str | None] = mapped_column(String(64))
    source_order_line_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(128))
    msku: Mapped[str | None] = mapped_column(Text)
    local_sku: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price_currency_code: Mapped[str | None] = mapped_column(String(3))
    order_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    order_total_currency_code: Mapped[str | None] = mapped_column(String(3))
    cancel_time_raw: Mapped[str | None] = mapped_column(Text)
    is_cancelled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    is_valid_sample: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    sample_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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


class WalmartRefundBusinessAmount(Base):
    __tablename__ = "dws_walmart_refund_business_amounts"
    __table_args__ = (
        UniqueConstraint("refund_fact_id"),
        CheckConstraint(
            "calculation_status IN ('calculated', 'order_not_matched', "
            "'unit_price_missing', 'quantity_missing')",
            name="ck_refund_business_calculation_status",
        ),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate < 1",
            name="ck_refund_business_commission_rate_range",
        ),
        Index(
            "ix_dws_walmart_refund_business_amounts_business_date",
            "business_date_la",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    refund_fact_id: Mapped[UUID] = mapped_column(
        ForeignKey("fact_walmart_refund_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    business_date_la: Mapped[date] = mapped_column(Date, nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str | None] = mapped_column(String(128))
    local_sku: Mapped[str | None] = mapped_column(Text)
    source_order_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fact_walmart_order_items.id", ondelete="SET NULL")
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_refund_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    net_refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    provider_refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    provider_refund_currency_code: Mapped[str | None] = mapped_column(String(3))
    calculation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
