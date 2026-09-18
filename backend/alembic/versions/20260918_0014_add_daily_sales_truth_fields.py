"""Add auditable Daily Sales truth and future actual-cost slots.

Revision ID: 20260918_0014
Revises: 20260917_0013
Create Date: 2026-09-18

Schema only. This migration does not backfill data or call external services.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260918_0014"
down_revision: str | Sequence[str] | None = "20260917_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _amount(name: str, *, nullable: bool = True, server_default: str | None = None) -> sa.Column:
    return sa.Column(
        name,
        sa.Numeric(18, 4),
        nullable=nullable,
        server_default=sa.text(server_default) if server_default is not None else None,
    )


def upgrade() -> None:
    for column in (
        _amount("gross_sales_qty", nullable=False, server_default="0"),
        _amount("gross_order_count", nullable=False, server_default="0"),
        _amount("gross_sales_amount", nullable=False, server_default="0"),
        _amount("sample_order_count", nullable=False, server_default="0"),
        _amount("sample_qty", nullable=False, server_default="0"),
        _amount("cost_quantity", nullable=False, server_default="0"),
        _amount("wfs_fee_expected_unit_amount"),
        _amount("wfs_fee_expected_total_amount"),
        _amount("wfs_fee_actual_total_amount"),
        _amount("wfs_fee_variance_amount"),
        sa.Column("wfs_fee_variance_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("wfs_fee_source", sa.String(64), nullable=True),
        _amount("purchase_cost_estimated_total_usd"),
        _amount("purchase_cost_actual_total_usd"),
        sa.Column("purchase_cost_source", sa.String(64), nullable=True),
        _amount("first_leg_cost_estimated_total_usd"),
        _amount("first_leg_cost_actual_total_usd"),
        sa.Column("first_leg_cost_source", sa.String(64), nullable=True),
        _amount("storage_fee_estimated_total_amount"),
        _amount("storage_fee_actual_total_amount"),
        sa.Column("storage_fee_source", sa.String(64), nullable=True),
        sa.Column("commission_source", sa.String(64), nullable=True),
        sa.Column(
            "calculation_warnings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    ):
        op.add_column("mart_daily_sales_item_day", column)

    op.drop_constraint(
        "uq_mart_daily_sales_item_day_business_date_la",
        "mart_daily_sales_item_day",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_mart_daily_sales_item_day_business_identity",
        "mart_daily_sales_item_day",
        ["business_date_la", "source_account_ref", "store_id", "item_id", "msku"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_mart_daily_sales_item_day_business_identity",
        "mart_daily_sales_item_day",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_mart_daily_sales_item_day_business_date_la",
        "mart_daily_sales_item_day",
        ["business_date_la", "source_account_ref", "store_id", "item_id"],
    )

    for name in (
        "calculation_warnings_json",
        "commission_source",
        "storage_fee_source",
        "storage_fee_actual_total_amount",
        "storage_fee_estimated_total_amount",
        "first_leg_cost_source",
        "first_leg_cost_actual_total_usd",
        "first_leg_cost_estimated_total_usd",
        "purchase_cost_source",
        "purchase_cost_actual_total_usd",
        "purchase_cost_estimated_total_usd",
        "wfs_fee_source",
        "wfs_fee_variance_rate",
        "wfs_fee_variance_amount",
        "wfs_fee_actual_total_amount",
        "wfs_fee_expected_total_amount",
        "wfs_fee_expected_unit_amount",
        "cost_quantity",
        "sample_qty",
        "sample_order_count",
        "gross_sales_amount",
        "gross_order_count",
        "gross_sales_qty",
    ):
        op.drop_column("mart_daily_sales_item_day", name)
