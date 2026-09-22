"""add business rule operation logs

Revision ID: 20260921_0013_business_rule_operation_logs
Revises: 20260921_0012_extend_store_commission_rule_scope
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0013_business_rule_operation_logs"
down_revision: str | Sequence[str] | None = "20260921_0012_extend_store_commission_rule_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_rule_operation_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_account_ref", sa.Text(), nullable=False),
        sa.Column("platform_code", sa.Text(), nullable=False, server_default="walmart"),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("store_id", sa.Text(), nullable=True),
        sa.Column("rule_scope", sa.Text(), nullable=True),
        sa.Column("item_ids", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("price_min_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("price_max_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("days_recalculated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_sales_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_profit_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actor_ref", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_check_constraint(
        "ck_business_rule_operation_logs_operation_type",
        "business_rule_operation_logs",
        "operation_type in ('commission_recalculate','commission_upsert','commission_deactivate')",
    )
    op.create_check_constraint(
        "ck_business_rule_operation_logs_status",
        "business_rule_operation_logs",
        "status in ('queued','running','succeeded','failed')",
    )

    op.create_index(
        "ix_business_rule_operation_logs_store_created",
        "business_rule_operation_logs",
        ["source_account_ref", "platform_code", "store_id", "created_at"],
    )

    op.create_index(
        "ux_business_rule_active_store_recalculate",
        "business_rule_operation_logs",
        ["source_account_ref", "platform_code", "store_id"],
        unique=True,
        postgresql_where=sa.text(
            "operation_type='commission_recalculate' and status in ('queued','running')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_business_rule_active_store_recalculate",
        table_name="business_rule_operation_logs",
    )
    op.drop_index(
        "ix_business_rule_operation_logs_store_created",
        table_name="business_rule_operation_logs",
    )
    op.drop_constraint(
        "ck_business_rule_operation_logs_status",
        "business_rule_operation_logs",
        type_="check",
    )
    op.drop_constraint(
        "ck_business_rule_operation_logs_operation_type",
        "business_rule_operation_logs",
        type_="check",
    )
    op.drop_table("business_rule_operation_logs")
