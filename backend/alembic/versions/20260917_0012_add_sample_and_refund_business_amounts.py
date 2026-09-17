"""Add sample-order fact and governed refund business amounts.

Revision ID: 20260917_0012
Revises: 20260917_0011
Create Date: 2026-09-17

Schema only. This migration does not backfill data or call external services.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260917_0012"
down_revision: str | Sequence[str] | None = "20260917_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_walmart_sample_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_date_utc_minus_7", sa.Date(), nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(64),
            server_default=sa.text("'UTC-07:00'"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_order_id", sa.String(128), nullable=True),
        sa.Column("platform_order_no", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("platform_code", sa.String(64), nullable=True),
        sa.Column("source_order_line_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price_currency_code", sa.String(3), nullable=True),
        sa.Column("order_total_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("order_total_currency_code", sa.String(3), nullable=True),
        sa.Column("cancel_time_raw", sa.Text(), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_valid_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sample_rule_version", sa.String(64), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_sample_quantity_nonnegative"),
        sa.CheckConstraint(
            "unit_price_amount IS NULL OR unit_price_amount >= 0",
            name="ck_sample_unit_price_nonnegative",
        ),
        sa.CheckConstraint(
            "order_total_amount IS NULL OR order_total_amount >= 0",
            name="ck_sample_order_total_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_walmart_sample_order_items")),
        sa.UniqueConstraint(
            "source_account_ref",
            "platform_order_no",
            "source_order_line_id",
            name=op.f("uq_fact_walmart_sample_order_items_source_account_ref"),
        ),
    )
    op.create_index(
        "ix_fact_walmart_sample_order_items_business_date",
        "fact_walmart_sample_order_items",
        ["business_date_utc_minus_7"],
        unique=False,
    )
    op.create_index(
        "ix_fact_walmart_sample_order_items_store_sku",
        "fact_walmart_sample_order_items",
        ["store_id", "local_sku"],
        unique=False,
    )

    op.create_table(
        "dws_walmart_refund_business_amounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "refund_fact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fact_walmart_refund_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column(
            "source_order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fact_walmart_order_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_sales_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("gross_refund_sales_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("commission_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("commission_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_refund_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("provider_refund_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("provider_refund_currency_code", sa.String(3), nullable=True),
        sa.Column("calculation_status", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "calculation_status IN ('calculated','order_not_matched','unit_price_missing','quantity_missing')",
            name="ck_refund_business_calculation_status",
        ),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate < 1",
            name="ck_refund_business_commission_rate_range",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dws_walmart_refund_business_amounts")),
        sa.UniqueConstraint(
            "refund_fact_id",
            name=op.f("uq_dws_walmart_refund_business_amounts_refund_fact_id"),
        ),
    )
    op.create_index(
        "ix_dws_walmart_refund_business_amounts_business_date",
        "dws_walmart_refund_business_amounts",
        ["business_date_la"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dws_walmart_refund_business_amounts_business_date",
        table_name="dws_walmart_refund_business_amounts",
    )
    op.drop_table("dws_walmart_refund_business_amounts")
    op.drop_index(
        "ix_fact_walmart_sample_order_items_store_sku",
        table_name="fact_walmart_sample_order_items",
    )
    op.drop_index(
        "ix_fact_walmart_sample_order_items_business_date",
        table_name="fact_walmart_sample_order_items",
    )
    op.drop_table("fact_walmart_sample_order_items")
