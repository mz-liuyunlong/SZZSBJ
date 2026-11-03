"""Lingxing WFS cost valuation flow ODS (PRPs/wfs-inventory-claim.md §7.1, PR 1).

Creates ods_lingxing_wfs_cost_valuation_flow only: the single ODS table for interface
LX-8437AD0BCB9E, read by the inventory claim page and by settlement profit V2
(is_current = true). Identity is (raw_request_ref_id, source_item_ordinal); no business
column, including serial_number, is unique. No data is written, no existing table is
altered, and no sync is enabled. Downgrade drops exactly this table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261103_0073_wfs_cost_valuation_flow"
down_revision: str | Sequence[str] | None = "20261103_0072_fin_settle_profit_v2"
branch_labels = None
depends_on = None

TABLE = "ods_lingxing_wfs_cost_valuation_flow"
INDEXES = (
    "ix_wfs_cost_flow_current_settlement",
    "ix_wfs_cost_flow_current_store_msku",
    "ix_wfs_cost_flow_current_type_date",
    "ix_wfs_cost_flow_run",
)


def upgrade() -> None:
    op.create_table(
        "ods_lingxing_wfs_cost_valuation_flow",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_request_ref_id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("source_item_ordinal", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("superseded_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("serial_number", sa.String(length=32), nullable=True),
        sa.Column("date_local", sa.DateTime(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("store_code", sa.String(length=16), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=True),
        sa.Column("store_mapping_status", sa.String(length=16), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("gtin", sa.Text(), nullable=True),
        sa.Column("local_sku", sa.Text(), nullable=True),
        sa.Column("business_type", sa.String(length=32), nullable=False),
        sa.Column("business_name", sa.Text(), nullable=True),
        sa.Column("business_desc", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("business_number", sa.Text(), nullable=True),
        sa.Column("order_number", sa.Text(), nullable=True),
        sa.Column("cost_source", sa.Text(), nullable=True),
        sa.Column("order_base_purchase_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("purchase_total_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("order_base_logistics_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("logistics_total_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("order_base_other_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("other_total_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(store_mapping_status = 'mapped') = (store_id IS NOT NULL)",
            name="wfs_cost_flow_store_mapping_consistent",
        ),
        sa.CheckConstraint(
            "store_mapping_status IN ('mapped', 'unmapped')",
            name="wfs_cost_flow_store_mapping_status",
        ),
        sa.CheckConstraint(
            "NOT is_current OR superseded_by_run_id IS NULL",
            name="wfs_cost_flow_current_not_superseded",
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR length(currency_code) = 3", name="wfs_cost_flow_currency_code"
        ),
        sa.CheckConstraint("source_item_ordinal >= 0", name="wfs_cost_flow_ordinal_nonnegative"),
        sa.CheckConstraint("window_end >= window_start", name="wfs_cost_flow_window_order"),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"],
            ["ods_api_raw_request_refs.id"],
            name="fk_wfs_cost_flow_raw_ref",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["gov_integration_sync_runs.id"],
            name="fk_wfs_cost_flow_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_run_id"],
            ["gov_integration_sync_runs.id"],
            name="fk_wfs_cost_flow_superseded_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_wfs_cost_valuation_flow")),
        sa.UniqueConstraint(
            "raw_request_ref_id", "source_item_ordinal", name="uq_wfs_cost_flow_request_ordinal"
        ),
    )
    op.create_index(
        "ix_wfs_cost_flow_current_settlement",
        "ods_lingxing_wfs_cost_valuation_flow",
        ["source_account_ref", "settlement_date"],
        unique=False,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_wfs_cost_flow_current_store_msku",
        "ods_lingxing_wfs_cost_valuation_flow",
        ["source_account_ref", "store_code", "msku"],
        unique=False,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_wfs_cost_flow_current_type_date",
        "ods_lingxing_wfs_cost_valuation_flow",
        ["source_account_ref", "is_current", "business_type", "business_date"],
        unique=False,
    )
    op.create_index(
        "ix_wfs_cost_flow_run", "ods_lingxing_wfs_cost_valuation_flow", ["run_id"], unique=False
    )


def downgrade() -> None:
    for name in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
