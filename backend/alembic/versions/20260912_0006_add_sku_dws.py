"""Add reusable current SKU profile DWS table.

Revision ID: 20260912_0006
Revises: 20260912_0005
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260912_0006"
down_revision: str | Sequence[str] | None = "20260912_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dws_sku_base_profile_current",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        sa.Column("product_volume_cm3", sa.Numeric(18, 4), nullable=True),
        sa.Column("package_volume_cm3", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_volume_cm3", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_volume_cbm", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_net_weight_kg", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_gross_weight_kg", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_box_weight_kg", sa.Numeric(18, 4), nullable=True),
        sa.Column("purchase_cost_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("purchase_cost_currency_code", sa.String(3), nullable=True),
        sa.Column("us_first_leg_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("us_first_leg_currency", sa.String(3), nullable=True),
        sa.Column("unit_first_leg_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_first_leg_currency", sa.String(3), nullable=True),
        sa.Column("has_customs_info", sa.Boolean(), nullable=False),
        sa.Column("has_package_info", sa.Boolean(), nullable=False),
        sa.Column("has_logistics_info", sa.Boolean(), nullable=False),
        sa.Column("missing_fields_json", postgresql.JSONB(), nullable=False),
        sa.Column("data_quality_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "data_quality_score BETWEEN 0 AND 100",
            name=op.f("ck_dws_sku_base_profile_current_quality_score"),
        ),
        sa.CheckConstraint(
            "(purchase_cost_cny IS NULL AND purchase_cost_currency_code IS NULL) OR "
            "(purchase_cost_cny IS NOT NULL AND purchase_cost_currency_code = 'CNY')",
            name=op.f("ck_dws_sku_base_profile_current_purchase_currency"),
        ),
        sa.CheckConstraint(
            "(us_first_leg_cost IS NULL AND us_first_leg_currency IS NULL) OR "
            "(us_first_leg_cost IS NOT NULL AND us_first_leg_currency IS NOT NULL)",
            name=op.f("ck_dws_sku_base_profile_current_first_leg_currency"),
        ),
        sa.CheckConstraint(
            "(unit_first_leg_cost IS NULL AND unit_first_leg_currency IS NULL) OR "
            "(unit_first_leg_cost IS NOT NULL AND unit_first_leg_currency IS NOT NULL)",
            name=op.f("ck_dws_sku_base_profile_current_unit_first_leg_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["dwd_lingxing_sku_identity_index.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dwd_lingxing_sku_product_info_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dws_sku_base_profile_current")),
        sa.UniqueConstraint(
            "provider",
            "source_account_ref",
            "lingxing_sku_id",
            name="uq_dws_sku_base_profile_grain",
        ),
        sa.UniqueConstraint(
            "source_snapshot_id", name=op.f("uq_dws_sku_base_profile_current_source_snapshot_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("dws_sku_base_profile_current")
