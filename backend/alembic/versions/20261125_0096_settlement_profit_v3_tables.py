"""0096：结算利润 V3 建表（PRP finance-settlement-profit-v3 §6.2，PR-1）。

18 张表：ODS 4（领星发货单 / 发货明细 / 销售出库单、评价加速器快照）、FACT 3、MART 4、
MANUAL 5、CFG 2。只建表，不写同步、计算和接口；表都从空开始，默认值只在生产库配置。

回滚：任何一张表有数据就拒绝（rollback blocked），不执行 DELETE / TRUNCATE（PRP §13）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261125_0096_settlement_profit_v3_tables"
down_revision: str | Sequence[str] | None = "20261124_0095_sync_work_item_provider_error"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "ods_lingxing_fin_shipping_lists",
    "ods_lingxing_fin_shipping_detail_items",
    "ods_lingxing_fin_wms_outbound_orders",
    "ods_walmart_review_accelerator_snapshots",
    "fact_settlement_order_lines",
    "fact_settlement_store_month_items",
    "fact_settlement_post_close_diffs",
    "mart_settlement_profit_item_month",
    "mart_settlement_order_review",
    "mart_settlement_reconcile_store_period",
    "mart_settlement_no_order_flags",
    "manual_settlement_cost_entries",
    "manual_settlement_sem_month",
    "manual_settlement_order_adjustments",
    "manual_settlement_review_actions",
    "manual_settlement_month_close",
    "cfg_finance_settlement_settings",
    "cfg_finance_owner_tag_rules",
)


def upgrade() -> None:
    op.create_table(
        "cfg_finance_owner_tag_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tag_name", sa.String(length=128), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cfg_finance_owner_tag_rules")),
        sa.UniqueConstraint("tag_name", name="uq_cfg_finance_owner_tag_rule"),
    )
    op.create_table(
        "cfg_finance_settlement_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("setting_key", sa.String(length=64), nullable=False),
        sa.Column("effective_month", sa.Date(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "setting_key IN ('review_accelerator_price_formula', 'company_cost_allocation', "
            "'fixed_cost_fallback', 'review_accelerator_snapshot_frequency', 'no_order_months', "
            "'bill_month_cutoff_day', 'wfs_carrier_provider_ids')",
            name="setting_key",
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM effective_month) = 1", name="effective_month_first_day"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cfg_finance_settlement_settings")),
        sa.UniqueConstraint(
            "setting_key", "effective_month", name="uq_cfg_finance_settlement_setting"
        ),
    )
    op.create_table(
        "fact_settlement_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("line_kind", sa.String(length=16), nullable=False),
        sa.Column("fulfillment_type", sa.String(length=16), nullable=False),
        sa.Column("platform_order_no", sa.String(length=64), nullable=False),
        sa.Column("order_line_no", sa.String(length=32), nullable=False),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("item_id", sa.String(length=64), nullable=True),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "transaction_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sales_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "refund_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "promotion_usd",
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
            "wfs_fulfillment_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "mcf_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_allocated_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "settlement_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("purchase_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("last_leg_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("cost_total_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("cost_total_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "cost_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cost_entry_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("auto_passed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "source_run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=8), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("fulfillment_type IN ('wfs', 'seller')", name="fulfillment_type"),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="fx_status"),
        sa.CheckConstraint("line_kind IN ('sale', 'refund', 'mcf')", name="line_kind"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_order_lines")),
        sa.UniqueConstraint(
            "store_id",
            "period_key",
            "calc_version",
            "line_key",
            name="uq_fact_settlement_order_line",
        ),
    )
    op.create_index(
        "ix_fact_settlement_order_lines_current",
        "fact_settlement_order_lines",
        ["store_id", "period_key", "is_current"],
        unique=False,
    )
    op.create_index(
        "ix_fact_settlement_order_lines_item",
        "fact_settlement_order_lines",
        ["store_id", "bill_month", "item_id"],
        unique=False,
    )
    op.create_table(
        "fact_settlement_post_close_diffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=False),
        sa.Column("new_calc_version", sa.Integer(), nullable=True),
        sa.Column(
            "old_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "new_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'open'"), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved_by_unlock')", name="status"
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_post_close_diffs")),
        sa.UniqueConstraint(
            "store_id",
            "bill_month",
            "line_key",
            "detected_at",
            name="uq_fact_settlement_post_close_diff",
        ),
    )
    op.create_table(
        "fact_settlement_store_month_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("transaction_type", sa.String(length=128), nullable=True),
        sa.Column(
            "amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("amount_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("allocation_method", sa.String(length=32), nullable=True),
        sa.Column(
            "allocation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "assign_status",
            sa.String(length=16),
            server_default=sa.text("'assigned'"),
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=8), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assign_status IN ('assigned', 'pending', 'not_applicable')", name="assign_status"
        ),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="fx_status"),
        sa.CheckConstraint(
            "review_status IN ('pending', 'auto', 'first_passed', 'final_passed', 'rejected')",
            name="review_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('review_accelerator', 'discount_back', 'transfer_fee', 'mcf', "
            "'storage_fee', 'other_wfs_service', 'company_cost', 'unassigned_bill', "
            "'unassigned_wfs')",
            name="source_kind",
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_settlement_store_month_items")),
        sa.UniqueConstraint(
            "store_id",
            "bill_month",
            "source_kind",
            "source_ref",
            name="uq_fact_settlement_store_month_item",
        ),
    )
    op.create_index(
        "ix_fact_settlement_store_month_items_line",
        "fact_settlement_store_month_items",
        ["line_key"],
        unique=False,
    )
    op.create_table(
        "manual_settlement_cost_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("shipping_list_code", sa.String(length=64), nullable=True),
        sa.Column("outbound_order_no", sa.String(length=64), nullable=True),
        sa.Column("scope_ref", sa.String(length=80), nullable=False),
        sa.Column("purchase_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("last_leg_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("entry_kind", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "prefilled",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending_first'"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_kind <> 'override' OR coalesce(reason, '') <> ''", name="override_reason"
        ),
        sa.CheckConstraint("entry_kind IN ('confirm', 'override')", name="entry_kind"),
        sa.CheckConstraint(
            "status IN ('pending_first', 'first_passed', 'final_passed', 'rejected', 'revoked')",
            name="status",
        ),
        sa.CheckConstraint(
            "(shipping_list_code IS NULL) <> (outbound_order_no IS NULL)", name="one_scope"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_cost_entries")),
        sa.UniqueConstraint("idempotency_key", name="uq_manual_settlement_cost_entry_idem"),
    )
    op.create_index(
        "uq_manual_settlement_cost_entry_active",
        "manual_settlement_cost_entries",
        ["store_id", "msku", "scope_ref"],
        unique=True,
        postgresql_where=sa.text("status <> 'revoked'"),
    )
    op.create_table(
        "manual_settlement_month_close",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column(
            "totals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "acted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "action <> 'unlock' OR coalesce(reason, '') <> ''", name="unlock_needs_reason"
        ),
        sa.CheckConstraint("action IN ('close', 'unlock')", name="action"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_month_close")),
        sa.UniqueConstraint(
            "store_id", "bill_month", "seq", name="uq_manual_settlement_month_close"
        ),
    )
    op.create_table(
        "manual_settlement_order_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=True),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount_field", sa.String(length=64), nullable=True),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("target_item_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column(
            "review_status",
            sa.String(length=16),
            server_default=sa.text("'pending_first'"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind <> 'amount' OR amount_usd IS NOT NULL", name="amount_value"),
        sa.CheckConstraint(
            "kind <> 'assign_item' OR target_item_id IS NOT NULL", name="assign_item"
        ),
        sa.CheckConstraint("kind IN ('amount', 'assign_item', 'note')", name="kind"),
        sa.CheckConstraint(
            "review_status IN ('pending_first', 'first_passed', 'final_passed', 'rejected', "
            "'revoked')",
            name="review_status",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="status"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_order_adjustments")),
        sa.UniqueConstraint("idempotency_key", name="uq_manual_settlement_adjustment_idem"),
    )
    op.create_index(
        "ix_manual_settlement_adjustments_line",
        "manual_settlement_order_adjustments",
        ["line_key"],
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
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=True),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "acted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "decision = 'pass' OR coalesce(comment, '') <> ''", name="reject_needs_comment"
        ),
        sa.CheckConstraint("decision IN ('pass', 'reject', 'revert')", name="decision"),
        sa.CheckConstraint("stage IN ('first', 'final')", name="stage"),
        sa.CheckConstraint(
            "target_kind IN ('order_line', 'store_item', 'cost_entry', 'adjustment')",
            name="target_kind",
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_review_actions")),
    )
    op.create_index(
        "ix_manual_settlement_review_line",
        "manual_settlement_review_actions",
        ["line_key", "acted_at"],
        unique=False,
    )
    op.create_index(
        "ix_manual_settlement_review_month",
        "manual_settlement_review_actions",
        ["store_id", "bill_month"],
        unique=False,
    )
    op.create_table(
        "manual_settlement_sem_month",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column(
            "sem_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("source_file_name", sa.String(length=255), nullable=True),
        sa.Column("imported_by", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_sem_month")),
        sa.UniqueConstraint("store_id", "item_id", "bill_month", name="uq_manual_settlement_sem"),
    )
    op.create_table(
        "mart_settlement_no_order_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column("months_without_order", sa.Integer(), nullable=False),
        sa.Column("last_order_date", sa.Date(), nullable=True),
        sa.Column("wfs_inventory_qty", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("inventory_snapshot_date", sa.Date(), nullable=True),
        sa.Column(
            "storage_fee_cum_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "disposal_loss_cum_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_no_order_flags")),
        sa.UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_no_order_flag"
        ),
    )
    op.create_table(
        "mart_settlement_order_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("line_key", sa.String(length=255), nullable=False),
        sa.Column("row_kind", sa.String(length=16), nullable=False),
        sa.Column("platform_order_no", sa.String(length=64), nullable=True),
        sa.Column("item_id", sa.String(length=64), nullable=True),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column(
            "transaction_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "settlement_amount_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("cost_total_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("first_reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("final_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'auto', 'first_passed', 'final_passed', 'rejected')",
            name="review_status",
        ),
        sa.CheckConstraint(
            "row_kind IN ('order', 'store_item', 'reconcile_diff')", name="row_kind"
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_order_review")),
        sa.UniqueConstraint(
            "store_id", "period_key", "line_key", name="uq_mart_settlement_order_review"
        ),
    )
    op.create_index(
        "ix_mart_settlement_order_review_order",
        "mart_settlement_order_review",
        ["platform_order_no"],
        unique=False,
    )
    op.create_index(
        "ix_mart_settlement_order_review_status",
        "mart_settlement_order_review",
        ["store_id", "period_key", "review_status"],
        unique=False,
    )
    op.create_table(
        "mart_settlement_profit_item_month",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "sales_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "refund_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "promotion_usd",
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
            "wfs_fulfillment_fee_usd",
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
            "transfer_fee_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "mcf_fee_usd",
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
            "other_wfs_service_usd",
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
        sa.Column("packing_fee_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "ad_sp_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_sb_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_sv_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "sem_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("purchase_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("last_leg_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("cost_total_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("settlement_profit_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("settlement_profit_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("company_cost_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("net_profit_cny", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fx_month", sa.Date(), nullable=True),
        sa.Column(
            "fx_status", sa.String(length=8), server_default=sa.text("'missing'"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("fx_status IN ('final', 'missing')", name="fx_status"),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_profit_item_month")),
        sa.UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_profit_item_month"
        ),
    )
    op.create_index(
        "ix_mart_settlement_profit_item_month_owner",
        "mart_settlement_profit_item_month",
        ["owner_id", "bill_month"],
        unique=False,
    )
    op.create_table(
        "mart_settlement_reconcile_store_period",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.Date(), nullable=False),
        sa.Column(
            "bill_total_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "order_lines_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "item_allocated_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "store_items_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "store_columns_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "pending_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "diff_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wfs_detail_vs_bill_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "inbound_vs_bill_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_vs_bill_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "company_income_usd",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("calc_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.Column("frozen_calc_version", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'reconcile_failed', 'unassigned_pending')", name="status"
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM bill_month) = 1", name="bill_month_first_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_settlement_reconcile_store_period")),
        sa.UniqueConstraint("store_id", "period_key", name="uq_mart_settlement_reconcile_period"),
    )
    op.create_table(
        "ods_lingxing_fin_shipping_detail_items",
        sa.Column("shipping_list_code", sa.String(length=64), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("head_stock_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("per_firstlet_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("per_firstlet_actual", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("per_firstlet_expected", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("per_tax", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("wfs_stock_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("other_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("transportation_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("logistics_way", sa.Text(), nullable=True),
        sa.Column("logistics_provider_id", sa.String(length=64), nullable=True),
        sa.Column("head_fee_type", sa.String(length=32), nullable=True),
        sa.Column("value_source", sa.String(length=32), nullable=True),
        sa.Column("delivery_num", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_fin_shipping_detail_items")),
        sa.UniqueConstraint(
            "source_account_ref",
            "shipping_list_code",
            "msku",
            name="uq_ods_lx_fin_shipping_detail_item",
        ),
    )
    op.create_index(
        "ix_ods_lx_fin_shipping_detail_store_msku",
        "ods_lingxing_fin_shipping_detail_items",
        ["store_id", "msku"],
        unique=False,
    )
    op.create_table(
        "ods_lingxing_fin_shipping_lists",
        sa.Column("shipping_list_code", sa.String(length=64), nullable=False),
        sa.Column("shipping_list_status", sa.String(length=32), nullable=True),
        sa.Column("logistics_provider_id", sa.String(length=64), nullable=True),
        sa.Column("logistics_provider_name", sa.Text(), nullable=True),
        sa.Column("logistics_channel_name", sa.Text(), nullable=True),
        sa.Column("head_fee_type", sa.String(length=32), nullable=True),
        sa.Column("warehouse_id", sa.String(length=64), nullable=True),
        sa.Column("delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lx_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("shipping_list_code <> ''", name="shipping_list_code_not_blank"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_fin_shipping_lists")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "shipping_list_code",
            name="uq_ods_lx_fin_shipping_list",
        ),
    )
    op.create_table(
        "ods_lingxing_fin_wms_outbound_orders",
        sa.Column("outbound_order_no", sa.String(length=64), nullable=False),
        sa.Column("platform_order_no", sa.String(length=64), nullable=True),
        sa.Column("order_status", sa.String(length=32), nullable=True),
        sa.Column("logistics_fee", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("outbound_order_no <> ''", name="outbound_order_no_not_blank"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_fin_wms_outbound_orders")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "outbound_order_no",
            name="uq_ods_lx_fin_wms_outbound_order",
        ),
    )
    op.create_index(
        "ix_ods_lx_fin_wms_outbound_platform_order",
        "ods_lingxing_fin_wms_outbound_orders",
        ["store_id", "platform_order_no"],
        unique=False,
    )
    op.create_table(
        "ods_walmart_review_accelerator_snapshots",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("reviews_collected", sa.Integer(), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=32), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_raw_request_ref_id", sa.Uuid(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_row",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_walmart_review_accelerator_snapshots")),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "snapshot_date",
            "item_id",
            name="uq_ods_wm_review_accelerator_snapshot",
        ),
    )
    op.create_index(
        "ix_ods_wm_review_accelerator_item",
        "ods_walmart_review_accelerator_snapshots",
        ["store_id", "item_id", "snapshot_date"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        if bind.execute(sa.text(f"select 1 from {table} limit 1")).first() is not None:
            raise RuntimeError(f"rollback blocked: {table} has data")
    op.drop_index(
        "ix_ods_wm_review_accelerator_item", table_name="ods_walmart_review_accelerator_snapshots"
    )
    op.drop_table("ods_walmart_review_accelerator_snapshots")
    op.drop_index(
        "ix_ods_lx_fin_wms_outbound_platform_order",
        table_name="ods_lingxing_fin_wms_outbound_orders",
    )
    op.drop_table("ods_lingxing_fin_wms_outbound_orders")
    op.drop_table("ods_lingxing_fin_shipping_lists")
    op.drop_index(
        "ix_ods_lx_fin_shipping_detail_store_msku",
        table_name="ods_lingxing_fin_shipping_detail_items",
    )
    op.drop_table("ods_lingxing_fin_shipping_detail_items")
    op.drop_table("mart_settlement_reconcile_store_period")
    op.drop_index(
        "ix_mart_settlement_profit_item_month_owner", table_name="mart_settlement_profit_item_month"
    )
    op.drop_table("mart_settlement_profit_item_month")
    op.drop_index(
        "ix_mart_settlement_order_review_status", table_name="mart_settlement_order_review"
    )
    op.drop_index(
        "ix_mart_settlement_order_review_order", table_name="mart_settlement_order_review"
    )
    op.drop_table("mart_settlement_order_review")
    op.drop_table("mart_settlement_no_order_flags")
    op.drop_table("manual_settlement_sem_month")
    op.drop_index(
        "ix_manual_settlement_review_month", table_name="manual_settlement_review_actions"
    )
    op.drop_index("ix_manual_settlement_review_line", table_name="manual_settlement_review_actions")
    op.drop_table("manual_settlement_review_actions")
    op.drop_index(
        "ix_manual_settlement_adjustments_month", table_name="manual_settlement_order_adjustments"
    )
    op.drop_index(
        "ix_manual_settlement_adjustments_line", table_name="manual_settlement_order_adjustments"
    )
    op.drop_table("manual_settlement_order_adjustments")
    op.drop_table("manual_settlement_month_close")
    op.drop_index(
        "uq_manual_settlement_cost_entry_active",
        table_name="manual_settlement_cost_entries",
        postgresql_where=sa.text("status <> 'revoked'"),
    )
    op.drop_table("manual_settlement_cost_entries")
    op.drop_index(
        "ix_fact_settlement_store_month_items_line", table_name="fact_settlement_store_month_items"
    )
    op.drop_table("fact_settlement_store_month_items")
    op.drop_table("fact_settlement_post_close_diffs")
    op.drop_index("ix_fact_settlement_order_lines_item", table_name="fact_settlement_order_lines")
    op.drop_index(
        "ix_fact_settlement_order_lines_current", table_name="fact_settlement_order_lines"
    )
    op.drop_table("fact_settlement_order_lines")
    op.drop_table("cfg_finance_settlement_settings")
    op.drop_table("cfg_finance_owner_tag_rules")
