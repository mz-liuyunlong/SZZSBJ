from __future__ import annotations

# ruff: noqa: E501
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260927_0021_operation_plan_mvp"
down_revision: str | None = "20260924_0020_walmart_inventory_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ops_operation_plan_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("period_key", sa.String(32), nullable=False),
        sa.Column("period_start_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("period_type IN ('month', 'quarter')", name="ck_ops_plan_period_type"),
        sa.CheckConstraint("status IN ('draft', 'active', 'locked', 'closed')", name="ck_ops_plan_period_status"),
        sa.UniqueConstraint("platform_code", "period_type", "period_key", name="uq_ops_plan_period_identity"),
    )

    op.create_table(
        "ops_operation_product_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops_operation_plan_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform_code", sa.String(64), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("store_name_snapshot", sa.Text(), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("msku", sa.String(255), nullable=False),
        sa.Column("product_name_snapshot", sa.Text(), nullable=True),
        sa.Column("owner_ref", sa.String(255), nullable=True),
        sa.Column("owner_name_snapshot", sa.String(255), nullable=True),
        sa.Column("target_sales_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("target_gross_profit_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False, server_default="USD"),
        sa.Column("operation_status", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("plan_status", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("stock_status", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("adjusted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_sales_amount > 0", name="ck_ops_product_plan_sales_positive"),
        sa.CheckConstraint("target_gross_profit_amount >= 0", name="ck_ops_product_plan_profit_nonnegative"),
        sa.CheckConstraint("target_gross_profit_amount <= target_sales_amount", name="ck_ops_product_plan_profit_lte_sales"),
        sa.CheckConstraint("operation_status IN ('normal', 'new_product', 'clearance')", name="ck_ops_product_plan_operation_status"),
        sa.CheckConstraint("plan_status IN ('normal', 'lagging', 'severe_lagging', 'unplanned', 'clearance')", name="ck_ops_product_plan_plan_status"),
        sa.CheckConstraint("stock_status IN ('normal', 'risk')", name="ck_ops_product_plan_stock_status"),
        sa.CheckConstraint("source_type IN ('manual', 'import', 'batch_generate', 'system_suggested')", name="ck_ops_product_plan_source_type"),
        sa.UniqueConstraint(
            "period_id",
            "platform_code",
            "source_account_ref",
            "item_id",
            "msku",
            name="uq_ops_product_plan_identity",
        ),
    )
    op.create_index("ix_ops_product_plans_period_owner", "ops_operation_product_plans", ["period_id", "owner_ref"])
    op.create_index("ix_ops_product_plans_period_status", "ops_operation_product_plans", ["period_id", "plan_status", "operation_status", "stock_status"])
    op.create_index("ix_ops_product_plans_item_msku", "ops_operation_product_plans", ["item_id", "msku"])

    op.create_table(
        "ops_operation_plan_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops_operation_plan_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("existing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_plan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_plan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_policy", sa.String(32), nullable=False, server_default="skip_existing"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('uploaded', 'processing', 'completed', 'partial_completed', 'failed', 'cancelled')", name="ck_ops_plan_import_batch_status"),
        sa.CheckConstraint("conflict_policy IN ('skip_existing', 'overwrite_existing')", name="ck_ops_plan_import_batch_conflict_policy"),
    )
    op.create_index("ix_ops_plan_import_batches_period", "ops_operation_plan_import_batches", ["period_id", "created_at"])

    op.create_foreign_key(
        "fk_ops_product_plan_import_batch",
        "ops_operation_product_plans",
        "ops_operation_plan_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "ops_operation_plan_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops_operation_plan_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("item_id_raw", sa.Text(), nullable=True),
        sa.Column("msku_raw", sa.Text(), nullable=True),
        sa.Column("target_sales_raw", sa.Text(), nullable=True),
        sa.Column("target_gross_profit_raw", sa.Text(), nullable=True),
        sa.Column("remark_raw", sa.Text(), nullable=True),
        sa.Column("resolved_source_account_ref", sa.String(128), nullable=True),
        sa.Column("resolved_store_id", sa.String(128), nullable=True),
        sa.Column("resolved_store_name", sa.Text(), nullable=True),
        sa.Column("resolved_item_id", sa.String(128), nullable=True),
        sa.Column("resolved_sku", sa.String(255), nullable=True),
        sa.Column("resolved_msku", sa.String(255), nullable=True),
        sa.Column("resolved_product_name", sa.Text(), nullable=True),
        sa.Column("resolved_owner_ref", sa.String(255), nullable=True),
        sa.Column("resolved_owner_name", sa.String(255), nullable=True),
        sa.Column("target_sales_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("target_gross_profit_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("import_status", sa.String(32), nullable=False),
        sa.Column("imported_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops_operation_product_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("validation_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("import_status IN ('success', 'updated', 'skipped', 'failed')", name="ck_ops_plan_import_row_status"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_ops_plan_import_row_number"),
    )
    op.create_index("ix_ops_plan_import_rows_batch_status", "ops_operation_plan_import_rows", ["batch_id", "import_status"])

    op.create_table(
        "ops_operation_plan_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("product_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops_operation_product_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("before_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_ref", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ops_plan_events_plan_time", "ops_operation_plan_events", ["product_plan_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ops_plan_events_plan_time", table_name="ops_operation_plan_events")
    op.drop_table("ops_operation_plan_events")
    op.drop_index("ix_ops_plan_import_rows_batch_status", table_name="ops_operation_plan_import_rows")
    op.drop_table("ops_operation_plan_import_rows")
    op.drop_constraint("fk_ops_product_plan_import_batch", "ops_operation_product_plans", type_="foreignkey")
    op.drop_index("ix_ops_plan_import_batches_period", table_name="ops_operation_plan_import_batches")
    op.drop_table("ops_operation_plan_import_batches")
    op.drop_index("ix_ops_product_plans_item_msku", table_name="ops_operation_product_plans")
    op.drop_index("ix_ops_product_plans_period_status", table_name="ops_operation_product_plans")
    op.drop_index("ix_ops_product_plans_period_owner", table_name="ops_operation_product_plans")
    op.drop_table("ops_operation_product_plans")
    op.drop_table("ops_operation_plan_periods")
