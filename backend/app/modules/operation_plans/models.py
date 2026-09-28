from __future__ import annotations

# ruff: noqa: E501
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationPlanPeriod(Base):
    __tablename__ = "ops_operation_plan_periods"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    platform_code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class OperationProductPlan(Base):
    __tablename__ = "ops_operation_product_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    period_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_operation_plan_periods.id"), nullable=False
    )
    platform_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    store_name_snapshot: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    msku: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name_snapshot: Mapped[str | None] = mapped_column(Text)
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    owner_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    target_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_gross_profit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(16), default="USD", server_default="USD")
    operation_status: Mapped[str] = mapped_column(
        String(32), default="normal", server_default="normal"
    )
    plan_status: Mapped[str] = mapped_column(String(32), default="normal", server_default="normal")
    stock_status: Mapped[str] = mapped_column(String(32), default="normal", server_default="normal")
    remark: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", server_default="manual")
    import_batch_id: Mapped[UUID | None]
    adjusted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class OperationPlanImportBatch(Base):
    __tablename__ = "ops_operation_plan_import_batches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    period_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_operation_plan_periods.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int] = mapped_column(default=0, server_default="0")
    success_count: Mapped[int] = mapped_column(default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(default=0, server_default="0")
    warning_count: Mapped[int] = mapped_column(default=0, server_default="0")
    existing_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_plan_count: Mapped[int] = mapped_column(default=0, server_default="0")
    updated_plan_count: Mapped[int] = mapped_column(default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(default=0, server_default="0")
    conflict_policy: Mapped[str] = mapped_column(String(32), default="skip_existing")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationPlanImportRow(Base):
    __tablename__ = "ops_operation_plan_import_rows"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_operation_plan_import_batches.id"), nullable=False
    )
    row_number: Mapped[int]
    item_id_raw: Mapped[str | None] = mapped_column(Text)
    msku_raw: Mapped[str | None] = mapped_column(Text)
    target_sales_raw: Mapped[str | None] = mapped_column(Text)
    target_gross_profit_raw: Mapped[str | None] = mapped_column(Text)
    remark_raw: Mapped[str | None] = mapped_column(Text)
    resolved_source_account_ref: Mapped[str | None] = mapped_column(String(128))
    resolved_store_id: Mapped[str | None] = mapped_column(String(128))
    resolved_store_name: Mapped[str | None] = mapped_column(Text)
    resolved_item_id: Mapped[str | None] = mapped_column(String(128))
    resolved_sku: Mapped[str | None] = mapped_column(String(255))
    resolved_msku: Mapped[str | None] = mapped_column(String(255))
    resolved_product_name: Mapped[str | None] = mapped_column(Text)
    resolved_owner_ref: Mapped[str | None] = mapped_column(String(255))
    resolved_owner_name: Mapped[str | None] = mapped_column(String(255))
    target_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    target_gross_profit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    import_status: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_plan_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    validation_errors: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    validation_warnings: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class OperationPlanEvent(Base):
    __tablename__ = "ops_operation_plan_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_operation_product_plans.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
