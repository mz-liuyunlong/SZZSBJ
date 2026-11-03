"""Finance settlement profit V2 storage (PRP finance-settlement-profit-v2 §6.2, PR-1).

Creates FACT / MART / manual_ / cfg_ tables and the settlement-profit ODS tables only.
The Lingxing WFS cost valuation ODS (ods_lingxing_wfs_cost_valuation_flow) belongs to the
inventory-claim PRP and is not created here.  No data is written, no existing table is
altered, and no sync is enabled.  Downgrade drops exactly these tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261103_0072_fin_settle_profit_v2"
down_revision: str | Sequence[str] | None = "20261102_0071_skill_lib"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cfg_net_profit_allocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("effective_month", sa.Date(), nullable=False),
        sa.Column(
            "fixed_cny",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("15000"),
            nullable=False,
        ),
        sa.Column(
            "excluded_owner_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM effective_month) = 1", name="net_profit_cfg_first_day"
        ),
        sa.CheckConstraint("fixed_cny >= 0", name="net_profit_cfg_fixed_nonneg"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cfg_net_profit_allocation")),
        sa.UniqueConstraint("effective_month", name="uq_cfg_net_profit_allocation_month"),
    )
    op.create_table(
        "fact_inventory_movement_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_flow_id", sa.Uuid(), nullable=False),
        sa.Column("source_sync_batch_id", sa.Uuid(), nullable=True),
        sa.Column("store_code", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=True),
        sa.Column("store_mapping_status", sa.String(length=16), nullable=False),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column("business_type", sa.String(length=64), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("item_id", sa.String(length=128), nullable=True),
        sa.Column("owner_ref", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("movement_month", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("goods_value_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("goods_value_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("disposal_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=16), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(store_mapping_status = 'mapped') = (store_id IS NOT NULL)",
            name="inv_move_store_id_matches_mapping",
        ),
        sa.CheckConstraint(
            "category IN ('loss', 'non_loss', 'claim', 'unclassified', 'lx_adjust', 'unknown')",
            name="inv_move_category",
        ),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="inv_move_fx_status"),
        sa.CheckConstraint(
            "store_mapping_status IN ('mapped', 'unmapped')", name="inv_move_store_mapping"
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM movement_month) = 1", name="inv_move_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_inventory_movement_lines")),
        sa.UniqueConstraint(
            "source_flow_id", "calc_version", name="uq_fact_inventory_movement_lines_flow_version"
        ),
    )
    op.create_index(
        "ix_fact_inventory_movement_lines_month",
        "fact_inventory_movement_lines",
        ["store_id", "movement_month", "category"],
        unique=False,
    )
    op.create_index(
        "ix_fact_inventory_movement_lines_serial",
        "fact_inventory_movement_lines",
        ["serial_number"],
        unique=False,
    )
    op.create_table(
        "fact_settlement_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("report_key", sa.String(length=255), nullable=False),
        sa.Column("platform_order_no", sa.String(length=255), nullable=False),
        sa.Column("order_item_no", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("owner_ref", sa.String(length=255), nullable=True),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_match_status", sa.String(length=32), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "source_run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column(
            "sales_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "platform_subsidy_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "refund_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "commission_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wfs_fulfillment_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "return_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "tax_withheld_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wfs_service_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "storage_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "inbound_wpc_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_cost_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "review_accelerator_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "disposal_loss_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("promotion_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("packaging_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("purchase_cost_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_cost_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("goods_cost_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_profit_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_profit_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("net_profit_share_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=16), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="settle_line_fx_status"),
        sa.CheckConstraint("line_key <> ''", name="settle_line_key_not_blank"),
        sa.CheckConstraint(
            "review_status IN ('pending', 'auto', 'adjusted', "
            "'first_passed', 'final_passed', 'rejected')",
            name="settle_line_review_status",
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM bill_month) = 1", name="settle_line_bill_month_first_day"
        ),
        sa.CheckConstraint("calc_version >= 1", name="settle_line_calc_version_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_order_lines")),
        sa.UniqueConstraint(
            "store_id",
            "bill_month",
            "calc_version",
            "line_key",
            name="uq_fact_settlement_order_lines_line_key_version",
        ),
    )
    op.create_index(
        "ix_fact_settlement_order_lines_item_month",
        "fact_settlement_order_lines",
        ["store_id", "item_id", "bill_month"],
        unique=False,
    )
    op.create_index(
        "ix_fact_settlement_order_lines_line_key",
        "fact_settlement_order_lines",
        ["line_key"],
        unique=False,
    )
    op.create_index(
        "ix_fact_settlement_order_lines_order",
        "fact_settlement_order_lines",
        ["store_id", "bill_month", "platform_order_no", "order_item_no"],
        unique=False,
    )
    op.create_table(
        "fact_settlement_post_close_diffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diff_amount_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'open'"), nullable=False),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved_by_reopen')", name="post_close_status"
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM bill_month) = 1", name="post_close_bill_month_first_day"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_post_close_diffs")),
        sa.UniqueConstraint(
            "store_id",
            "bill_month",
            "line_key",
            "detected_at",
            name="uq_fact_settlement_post_close_diffs_identity",
        ),
    )
    op.create_table(
        "fact_settlement_unassigned_amounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("assigned_item_id", sa.String(length=128), nullable=True),
        sa.Column("adjustment_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status <> 'assigned' OR assigned_item_id IS NOT NULL",
            name="unassigned_assigned_has_item",
        ),
        sa.CheckConstraint("status IN ('pending', 'assigned', 'void')", name="unassigned_status"),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM bill_month) = 1", name="unassigned_bill_month_first_day"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_unassigned_amounts")),
        sa.UniqueConstraint(
            "store_id",
            "bill_month",
            "source_kind",
            "source_ref",
            name="uq_fact_settlement_unassigned_amounts_identity",
        ),
    )
    op.create_table(
        "manual_settlement_month_close",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_scope", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column("snapshot_totals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status <> 'reopened' OR (reopen_reason IS NOT NULL AND reopen_reason <> '')",
            name="month_close_reopen_reason",
        ),
        sa.CheckConstraint("status IN ('closed', 'reopened')", name="month_close_status"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="month_close_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_month_close")),
        sa.UniqueConstraint("store_scope", "bill_month", name="uq_manual_settlement_month_close"),
    )
    op.create_table(
        "manual_settlement_order_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('cost', 'amount', 'assign_item', 'note')", name="adjustment_kind"
        ),
        sa.CheckConstraint("reason <> ''", name="adjustment_reason_required"),
        sa.CheckConstraint(
            "status <> 'revoked' OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)",
            name="adjustment_revoked_audit",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="adjustment_status"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="adjustment_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_order_adjustments")),
        sa.UniqueConstraint("idempotency_key", name="uq_manual_settlement_adjustments_idem"),
    )
    op.create_index(
        "ix_manual_settlement_adjustments_line",
        "manual_settlement_order_adjustments",
        ["line_key", "status"],
        unique=False,
    )
    op.create_index(
        "ix_manual_settlement_adjustments_month",
        "manual_settlement_order_adjustments",
        ["store_id", "bill_month"],
        unique=False,
    )
    op.create_table(
        "manual_settlement_review_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("line_version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision <> 'reject' OR (comment IS NOT NULL AND comment <> '')",
            name="review_reject_needs_comment",
        ),
        sa.CheckConstraint("decision IN ('pass', 'reject')", name="review_decision"),
        sa.CheckConstraint("stage IN ('first', 'final')", name="review_stage"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="review_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_review_actions")),
        sa.UniqueConstraint(
            "idempotency_key", "line_key", name="uq_manual_settlement_review_idem_line"
        ),
    )
    op.create_index(
        "ix_manual_settlement_review_line",
        "manual_settlement_review_actions",
        ["line_key", "acted_at"],
        unique=False,
    )
    op.create_table(
        "mart_inventory_movement_month",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("goods_value_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("goods_value_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("disposal_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('loss', 'non_loss', 'claim', 'unclassified', 'lx_adjust', 'unknown')",
            name="inv_month_category",
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM month) = 1", name="inv_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_inventory_movement_month")),
        sa.UniqueConstraint(
            "store_id", "item_id", "month", "category", name="uq_mart_inventory_movement_key"
        ),
    )
    op.create_table(
        "mart_settlement_order_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=512), nullable=False),
        sa.Column(
            "row_kind", sa.String(length=16), server_default=sa.text("'order'"), nullable=False
        ),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("platform_order_no", sa.String(length=255), nullable=True),
        sa.Column("order_item_no", sa.String(length=128), nullable=True),
        sa.Column("item_id", sa.String(length=128), nullable=True),
        sa.Column("owner_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("profit_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("first_reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("final_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "row_kind <> 'order' OR (platform_order_no IS NOT NULL AND order_item_no IS NOT NULL)",
            name="order_review_order_identity",
        ),
        sa.CheckConstraint(
            "row_kind IN ('order', 'unassigned', 'reconcile_diff')", name="order_review_row_kind"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'auto', 'adjusted', 'first_passed', 'final_passed', 'rejected')",
            name="order_review_status",
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="order_review_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_order_review")),
        sa.UniqueConstraint(
            "store_id", "bill_month", "line_key", name="uq_mart_settlement_order_review_key"
        ),
    )
    op.create_index(
        "ix_mart_settlement_order_review_order",
        "mart_settlement_order_review",
        ["store_id", "bill_month", "platform_order_no", "order_item_no"],
        unique=False,
    )
    op.create_index(
        "ix_mart_settlement_order_review_status",
        "mart_settlement_order_review",
        ["bill_month", "status"],
        unique=False,
    )
    op.create_table(
        "mart_settlement_profit_item_month",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("owner_ref", sa.String(length=255), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column(
            "sales_quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("net_profit_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_margin_ratio", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("ad_scope_note", sa.String(length=64), nullable=True),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sales_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "platform_subsidy_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "refund_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "commission_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wfs_fulfillment_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "return_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "tax_withheld_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wfs_service_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "storage_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "inbound_wpc_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_cost_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "review_accelerator_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "disposal_loss_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("promotion_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("packaging_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("purchase_cost_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_cost_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("goods_cost_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_profit_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_profit_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("net_profit_share_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=16), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="profit_item_month_fx_status"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="profit_item_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_profit_item_month")),
        sa.UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_profit_item_month_key"
        ),
    )
    op.create_index(
        "ix_mart_settlement_profit_item_month_owner",
        "mart_settlement_profit_item_month",
        ["bill_month", "owner_ref"],
        unique=False,
    )
    op.create_table(
        "mart_settlement_reconcile_store_month",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("settlement_total_usd", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("order_level_total_usd", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "unassigned_pending_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("diff_usd", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "ad_daily_vs_settlement_diff_usd", sa.Numeric(precision=18, scale=4), nullable=True
        ),
        sa.Column("cross_month_disposal_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "fx_status", sa.String(length=16), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="reconcile_fx_status"),
        sa.CheckConstraint(
            "status IN ('ok', 'reconcile_failed', 'unassigned_pending')", name="reconcile_status"
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="reconcile_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_reconcile_store_month")),
        sa.UniqueConstraint("store_id", "bill_month", name="uq_mart_settlement_reconcile_key"),
    )
    op.create_table(
        "ods_lingxing_mp_profit_order_lines",
        sa.Column("platform_order_no", sa.String(length=255), nullable=False),
        sa.Column("order_item_no", sa.String(length=128), nullable=False),
        sa.Column("transaction_type", sa.String(length=64), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_id", sa.String(length=128), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("sales_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("promotion_fee_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "review_accelerator_fee_amount", sa.Numeric(precision=18, scale=4), nullable=True
        ),
        sa.Column(
            "currency_code", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("source_row_seq", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("platform_order_no <> ''", name="lx_profit_order_no_not_blank"),
        sa.ForeignKeyConstraint(
            ["source_raw_request_ref_id"],
            ["ods_api_raw_request_refs.id"],
            name=op.f(
                "fk_ods_lingxing_mp_profit_order_lines_source_raw_request_ref_id_ods_api_raw_request_refs"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_mp_profit_order_lines")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "platform_order_no",
            "order_item_no",
            "transaction_type",
            "settlement_date",
            "source_row_seq",
            name="uq_ods_lx_mp_profit_order_identity",
        ),
    )
    op.create_index(
        "ix_ods_lx_mp_profit_order_lookup",
        "ods_lingxing_mp_profit_order_lines",
        ["store_id", "platform_order_no", "gtin"],
        unique=False,
    )
    op.create_table(
        "ods_walmart_review_accelerator_snapshots",
        sa.Column("snapshot_report_key", sa.String(length=255), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("enrollment_status", sa.String(length=64), nullable=True),
        sa.Column("reviews_collected", sa.Integer(), nullable=False),
        sa.Column("sale_price_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price_amount", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "currency_code", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False
        ),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remote_job_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("source_row_seq", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("item_id <> ''", name="wm_review_accel_item_not_blank"),
        sa.CheckConstraint("snapshot_report_key <> ''", name="wm_review_accel_key_not_blank"),
        sa.CheckConstraint("reviews_collected >= 0", name="wm_review_accel_reviews_nonneg"),
        sa.ForeignKeyConstraint(
            ["source_raw_request_ref_id"],
            ["ods_api_raw_request_refs.id"],
            name=op.f(
                "fk_ods_walmart_review_accelerator_snapshots_source_raw_request_ref_id_ods_api_raw_request_refs"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_walmart_review_accelerator_snapshots")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "snapshot_report_key",
            "item_id",
            name="uq_ods_wm_review_accel_identity",
        ),
    )
    op.create_table(
        "ods_walmart_storage_fee_lines",
        sa.Column("report_id", sa.String(length=255), nullable=True),
        sa.Column("report_period_start", sa.Date(), nullable=False),
        sa.Column("report_period_end", sa.Date(), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=True),
        sa.Column("on_hand_quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("volume_cubic_feet", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("storage_fee_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "currency_code", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False
        ),
        sa.Column("remote_job_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("source_row_seq", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gtin <> ''", name="wm_storage_fee_gtin_not_blank"),
        sa.CheckConstraint(
            "report_period_end >= report_period_start", name="wm_storage_fee_period_order"
        ),
        sa.ForeignKeyConstraint(
            ["source_raw_request_ref_id"],
            ["ods_api_raw_request_refs.id"],
            name=op.f(
                "fk_ods_walmart_storage_fee_lines_source_raw_request_ref_id_ods_api_raw_request_refs"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_walmart_storage_fee_lines")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "report_period_start",
            "report_period_end",
            "gtin",
            name="uq_ods_wm_storage_fee_identity",
        ),
    )
    op.create_table(
        "ods_walmart_wfs_fee_detail_lines",
        sa.Column("report_id", sa.String(length=255), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("report_period_start", sa.Date(), nullable=True),
        sa.Column("report_period_end", sa.Date(), nullable=True),
        sa.Column("transaction_date_la", sa.Date(), nullable=True),
        sa.Column("fee_type", sa.String(length=128), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("item_id", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("fee_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "currency_code", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False
        ),
        sa.Column("remote_job_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("source_row_seq", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("report_id <> ''", name="wm_fee_detail_report_not_blank"),
        sa.ForeignKeyConstraint(
            ["source_raw_request_ref_id"],
            ["ods_api_raw_request_refs.id"],
            name=op.f(
                "fk_ods_walmart_wfs_fee_detail_lines_source_raw_request_ref_id_ods_api_raw_request_refs"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_walmart_wfs_fee_detail_lines")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "report_id",
            "line_no",
            name="uq_ods_wm_wfs_fee_detail_identity",
        ),
    )
    op.create_index(
        "ix_ods_wm_wfs_fee_detail_gtin_date",
        "ods_walmart_wfs_fee_detail_lines",
        ["store_id", "gtin", "transaction_date_la"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ods_wm_wfs_fee_detail_gtin_date", table_name="ods_walmart_wfs_fee_detail_lines"
    )
    op.drop_table("ods_walmart_wfs_fee_detail_lines")
    op.drop_table("ods_walmart_storage_fee_lines")
    op.drop_table("ods_walmart_review_accelerator_snapshots")
    op.drop_index(
        "ix_ods_lx_mp_profit_order_lookup", table_name="ods_lingxing_mp_profit_order_lines"
    )
    op.drop_table("ods_lingxing_mp_profit_order_lines")
    op.drop_table("mart_settlement_reconcile_store_month")
    op.drop_index(
        "ix_mart_settlement_profit_item_month_owner", table_name="mart_settlement_profit_item_month"
    )
    op.drop_table("mart_settlement_profit_item_month")
    op.drop_index(
        "ix_mart_settlement_order_review_order", table_name="mart_settlement_order_review"
    )
    op.drop_index(
        "ix_mart_settlement_order_review_status", table_name="mart_settlement_order_review"
    )
    op.drop_table("mart_settlement_order_review")
    op.drop_table("mart_inventory_movement_month")
    op.drop_index("ix_manual_settlement_review_line", table_name="manual_settlement_review_actions")
    op.drop_table("manual_settlement_review_actions")
    op.drop_index(
        "ix_manual_settlement_adjustments_line", table_name="manual_settlement_order_adjustments"
    )
    op.drop_index(
        "ix_manual_settlement_adjustments_month", table_name="manual_settlement_order_adjustments"
    )
    op.drop_table("manual_settlement_order_adjustments")
    op.drop_table("manual_settlement_month_close")
    op.drop_table("fact_settlement_unassigned_amounts")
    op.drop_table("fact_settlement_post_close_diffs")
    op.drop_index(
        "ix_fact_settlement_order_lines_item_month", table_name="fact_settlement_order_lines"
    )
    op.drop_index(
        "ix_fact_settlement_order_lines_line_key", table_name="fact_settlement_order_lines"
    )
    op.drop_index("ix_fact_settlement_order_lines_order", table_name="fact_settlement_order_lines")
    op.drop_table("fact_settlement_order_lines")
    op.drop_index(
        "ix_fact_inventory_movement_lines_month", table_name="fact_inventory_movement_lines"
    )
    op.drop_index(
        "ix_fact_inventory_movement_lines_serial", table_name="fact_inventory_movement_lines"
    )
    op.drop_table("fact_inventory_movement_lines")
    op.drop_table("cfg_net_profit_allocation")
