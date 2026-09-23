"""Add PMC purchase board Gate 3 tables: DWD x3, DWS x3, manual cycle override, rule thresholds.

Revision ID: 20260922_0017
Revises: 20260921_0013_business_rule_operation_logs
Create Date: 2026-09-22

Gate 3 / PR G3-A of PRPs/pmc-purchase-board.md (Owner decision 2026-09-21 in #144:
no ItemID override table). Create-only; also seeds rule_purchase_thresholds version 1
with the business-rules v4 defaults. Running this against production still requires
PRODUCTION_MIGRATIONS_AUTHORIZED per the runbook and a separate written authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260922_0017"
down_revision: str | Sequence[str] | None = "20260921_0013_business_rule_operation_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DWD_PURCHASE_PLAN = "dwd_purchase_plan"
DWD_PURCHASE_ORDER = "dwd_purchase_order"
DWD_PURCHASE_ORDER_LINE_ITEM = "dwd_purchase_order_line_item"
DWS_PURCHASE_BOARD = "dws_purchase_board"
DWS_PURCHASE_SKU_CYCLE = "dws_purchase_sku_cycle"
DWS_PURCHASE_PENDING = "dws_purchase_pending"
MANUAL_PURCHASE_CYCLE_OVERRIDE = "manual_purchase_cycle_override"
RULE_PURCHASE_THRESHOLDS = "rule_purchase_thresholds"

ALL_TABLES = (
    DWD_PURCHASE_PLAN,
    DWD_PURCHASE_ORDER,
    DWD_PURCHASE_ORDER_LINE_ITEM,
    DWS_PURCHASE_BOARD,
    DWS_PURCHASE_SKU_CYCLE,
    DWS_PURCHASE_PENDING,
    MANUAL_PURCHASE_CYCLE_OVERRIDE,
    RULE_PURCHASE_THRESHOLDS,
)

# Business-rules v4 defaults == calculations.PurchaseThresholds() (seed version 1).
THRESHOLDS_V1 = {
    "rule_key": "pmc_purchase_thresholds",
    "version": 1,
    "s1_approval_days": 2,
    "s2_pending_days": 7,
    "default_cycle_days": 7,
    "arrival_ratio": "0.5000",
    "auto_exclude_below_days": 2,
    "sample_window": 5,
    "min_samples_for_average": 2,
    "unstable_min_samples": 5,
    "unstable_range_days": 3,
    "baseline_evict_at_samples": 5,
    "effective_from": "2026-08-01",
    "is_active": True,
    "approved_by": "mz-liuyunlong (rules v3 2026-09-18; baseline eviction 2026-09-21)",
    "change_reason": "Initial version: docs/business-rules/pmc-purchase-rules.md v4 defaults",
}


def upgrade() -> None:
    op.create_table(
        DWD_PURCHASE_PLAN,
        sa.Column("plan_sn", sa.String(64), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("create_date", sa.Date(), nullable=True),
        sa.Column("expect_arrive_date", sa.Date(), nullable=True),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("store_attributed", sa.Boolean(), nullable=False),
        sa.Column("store_matched", sa.Boolean(), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("quantity_plan", sa.Integer(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("remark_item_id", sa.String(32), nullable=True),
        sa.Column("first_seen_pending_date", sa.Date(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_ods_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_update_time", sa.String(32), nullable=True),
        sa.Column("builder_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "char_length(trim(plan_sn)) > 0", name=op.f(f"ck_{DWD_PURCHASE_PLAN}_nonblank_plan_sn")
        ),
        sa.UniqueConstraint("source_account_ref", "plan_sn", name="uq_dwd_purchase_plan_sn"),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWD_PURCHASE_PLAN}")),
    )
    op.create_index("ix_dwd_purchase_plan_sku", DWD_PURCHASE_PLAN, ["sku"])
    op.create_index("ix_dwd_purchase_plan_status", DWD_PURCHASE_PLAN, ["status"])

    op.create_table(
        DWD_PURCHASE_ORDER,
        sa.Column("order_sn", sa.String(64), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("create_date", sa.Date(), nullable=True),
        sa.Column("quantity_total", sa.Integer(), nullable=True),
        sa.Column("quantity_receive", sa.Integer(), nullable=True),
        sa.Column("quantity_real", sa.Integer(), nullable=True),
        sa.Column("amount_total", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(16), nullable=True),
        sa.Column("purchase_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("shipping_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("other_fee", sa.Numeric(18, 4), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_ods_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_update_time", sa.String(32), nullable=True),
        sa.Column("builder_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint("source_account_ref", "order_sn", name="uq_dwd_purchase_order_sn"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWD_PURCHASE_ORDER}")),
        sa.CheckConstraint(
            "char_length(trim(order_sn)) > 0",
            name=op.f(f"ck_{DWD_PURCHASE_ORDER}_nonblank_order_sn"),
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_dwd_purchase_order_order_date", DWD_PURCHASE_ORDER, ["order_date"])
    op.create_index("ix_dwd_purchase_order_status", DWD_PURCHASE_ORDER, ["status"])

    op.create_table(
        DWD_PURCHASE_ORDER_LINE_ITEM,
        sa.Column("order_sn", sa.String(64), nullable=False),
        sa.Column("order_item_id", sa.String(64), nullable=False),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("plan_sn", sa.String(64), nullable=True),
        sa.Column("plan_key", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("plan_count", sa.Integer(), nullable=False),
        sa.Column("allocation_ratio", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_merged", sa.Boolean(), nullable=False),
        sa.Column("plan_found", sa.Boolean(), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("store_attributed", sa.Boolean(), nullable=False),
        sa.Column("store_matched", sa.Boolean(), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("quantity_plan", sa.Integer(), nullable=True),
        sa.Column("quantity_real", sa.Integer(), nullable=True),
        sa.Column("quantity_allocated", sa.Integer(), nullable=False),
        sa.Column("amount_allocated", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("expect_arrive_date", sa.Date(), nullable=True),
        sa.Column("remark_item_id", sa.String(32), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_ods_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_update_time", sa.String(32), nullable=True),
        sa.Column("builder_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "quantity_allocated >= 0",
            name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_quantity_allocated"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWD_PURCHASE_ORDER_LINE_ITEM}")),
        sa.UniqueConstraint(
            "source_account_ref",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dwd_purchase_order_line_item_key",
        ),
        sa.CheckConstraint(
            "line_ordinal >= 0", name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_line_ordinal")
        ),
        sa.CheckConstraint(
            "allocation_ratio >= 0 AND allocation_ratio <= 1",
            name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_allocation_ratio"),
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "char_length(trim(order_sn)) > 0",
            name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_nonblank_order_sn"),
        ),
        sa.CheckConstraint(
            "plan_count >= 0", name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_plan_count")
        ),
        sa.CheckConstraint(
            "char_length(trim(order_item_id)) > 0",
            name=op.f(f"ck_{DWD_PURCHASE_ORDER_LINE_ITEM}_nonblank_order_item_id"),
        ),
    )
    op.create_index(
        "ix_dwd_purchase_order_line_item_order_sn", DWD_PURCHASE_ORDER_LINE_ITEM, ["order_sn"]
    )
    op.create_index(
        "ix_dwd_purchase_order_line_item_plan_sn", DWD_PURCHASE_ORDER_LINE_ITEM, ["plan_sn"]
    )
    op.create_index("ix_dwd_purchase_order_line_item_sku", DWD_PURCHASE_ORDER_LINE_ITEM, ["sku"])
    op.create_index(
        "ix_dwd_purchase_order_line_item_store_id", DWD_PURCHASE_ORDER_LINE_ITEM, ["store_id"]
    )

    op.create_table(
        DWS_PURCHASE_BOARD,
        sa.Column("order_sn", sa.String(64), nullable=False),
        sa.Column("order_item_id", sa.String(64), nullable=False),
        sa.Column("plan_key", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("plan_sn", sa.String(64), nullable=True),
        sa.Column("plan_sns_json", postgresql.JSONB(), nullable=False),
        sa.Column("order_status", sa.Integer(), nullable=True),
        sa.Column("plan_status", sa.Integer(), nullable=True),
        sa.Column("stage_code", sa.String(8), nullable=False),
        sa.Column("stage_start", sa.Date(), nullable=True),
        sa.Column("threshold_days", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("overdue_days", sa.Integer(), nullable=False),
        sa.Column("alert_due_since", sa.Date(), nullable=True),
        sa.Column("stage_start_estimated", sa.Boolean(), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("store_name", sa.String(255), nullable=True),
        sa.Column("store_attributed", sa.Boolean(), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("msku", sa.String(255), nullable=True),
        sa.Column("gtin", sa.String(64), nullable=True),
        sa.Column("item_id", sa.String(32), nullable=True),
        sa.Column("item_id_source", sa.String(32), nullable=False),
        sa.Column("item_id_source_ref", sa.String(64), nullable=True),
        sa.Column("item_id_matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_id_match_status", sa.String(32), nullable=False),
        sa.Column("owner_uid", sa.String(255), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("fulfillment_type", sa.String(64), nullable=True),
        sa.Column("wfs_not_ready", sa.Boolean(), nullable=True),
        sa.Column("quantity_total", sa.Integer(), nullable=True),
        sa.Column("quantity_allocated", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("progress_ratio", sa.Numeric(18, 6), nullable=True),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("order_create_date", sa.Date(), nullable=True),
        sa.Column("plan_create_date", sa.Date(), nullable=True),
        sa.Column("arrival_date", sa.Date(), nullable=True),
        sa.Column("arrival_receipt_order_sn", sa.String(64), nullable=True),
        sa.Column("purchase_cycle_days", sa.Integer(), nullable=True),
        sa.Column("approval_cycle_days", sa.Integer(), nullable=True),
        sa.Column("sku_cycle_days", sa.Numeric(18, 4), nullable=True),
        sa.Column("sku_cycle_source", sa.String(32), nullable=True),
        sa.Column("sku_cycle_sample_count", sa.Integer(), nullable=True),
        sa.Column("sku_cycle_unstable", sa.Boolean(), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount_allocated", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount_total", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(16), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_lineage_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_id_source IN ('from_system_plan', 'from_plan_remark', 'from_packing_slip', "
            "'pending_packing_slip', 'unresolved')",
            name=op.f(f"ck_{DWS_PURCHASE_BOARD}_item_id_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWS_PURCHASE_BOARD}")),
        sa.UniqueConstraint(
            "source_account_ref",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dws_purchase_board_key",
        ),
        sa.CheckConstraint("overdue_days >= 0", name=op.f(f"ck_{DWS_PURCHASE_BOARD}_overdue_days")),
        sa.CheckConstraint(
            "stage_code IN ('S1', 'S2', 'S3', 'S4', 'S9', 'S0', 'UNKNOWN')",
            name=op.f(f"ck_{DWS_PURCHASE_BOARD}_stage_code"),
        ),
    )
    op.create_index("ix_dws_purchase_board_item_id", DWS_PURCHASE_BOARD, ["item_id"])
    op.create_index("ix_dws_purchase_board_order_date", DWS_PURCHASE_BOARD, ["order_date"])
    op.create_index("ix_dws_purchase_board_owner_uid", DWS_PURCHASE_BOARD, ["owner_uid"])
    op.create_index("ix_dws_purchase_board_sku", DWS_PURCHASE_BOARD, ["sku"])
    op.create_index("ix_dws_purchase_board_stage_code", DWS_PURCHASE_BOARD, ["stage_code"])
    op.create_index("ix_dws_purchase_board_store_id", DWS_PURCHASE_BOARD, ["store_id"])

    op.create_table(
        DWS_PURCHASE_SKU_CYCLE,
        sa.Column("sku", sa.String(255), nullable=False),
        sa.Column("value_days", sa.Numeric(18, 4), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_days", sa.Integer(), nullable=True),
        sa.Column("baseline_set_on", sa.Date(), nullable=True),
        sa.Column("lingxing_default_days", sa.Integer(), nullable=True),
        sa.Column("unstable", sa.Boolean(), nullable=False),
        sa.Column("range_days", sa.Integer(), nullable=True),
        sa.Column("samples_json", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_lineage_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWS_PURCHASE_SKU_CYCLE}")),
        sa.CheckConstraint(
            "source IN ('samples', 'baseline_mix', 'lingxing_default', 'no_baseline')",
            name=op.f(f"ck_{DWS_PURCHASE_SKU_CYCLE}_source"),
        ),
        sa.CheckConstraint(
            "sample_count >= 0", name=op.f(f"ck_{DWS_PURCHASE_SKU_CYCLE}_sample_count")
        ),
        sa.UniqueConstraint("source_account_ref", "sku", name="uq_dws_purchase_sku_cycle_sku"),
    )
    op.create_index("ix_dws_purchase_sku_cycle_unstable", DWS_PURCHASE_SKU_CYCLE, ["unstable"])

    op.create_table(
        DWS_PURCHASE_PENDING,
        sa.Column("pending_type", sa.String(32), nullable=False),
        sa.Column("order_sn", sa.String(64), nullable=False),
        sa.Column("order_item_id", sa.String(64), nullable=False),
        sa.Column("plan_key", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("plan_sn", sa.String(64), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("item_id", sa.String(32), nullable=True),
        sa.Column("item_id_source", sa.String(32), nullable=True),
        sa.Column("stage_code", sa.String(8), nullable=True),
        sa.Column("overdue_days", sa.Integer(), nullable=True),
        sa.Column("owner_uid", sa.String(255), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("detail_json", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_lineage_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref",
            "pending_type",
            "order_sn",
            "order_item_id",
            "plan_key",
            name="uq_dws_purchase_pending_key",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DWS_PURCHASE_PENDING}")),
        sa.CheckConstraint(
            "pending_type IN ('itemid_pending', 'wfs_not_ready', 'overdue')",
            name=op.f(f"ck_{DWS_PURCHASE_PENDING}_pending_type"),
        ),
    )
    op.create_index("ix_dws_purchase_pending_owner_uid", DWS_PURCHASE_PENDING, ["owner_uid"])
    op.create_index("ix_dws_purchase_pending_type", DWS_PURCHASE_PENDING, ["pending_type"])

    op.create_table(
        MANUAL_PURCHASE_CYCLE_OVERRIDE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("purchase_order_sn", sa.String(64), nullable=True),
        sa.Column("value_days", sa.Integer(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("before_json", postgresql.JSONB(), nullable=False),
        sa.Column("after_json", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator_ref", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f(f"ck_{MANUAL_PURCHASE_CYCLE_OVERRIDE}_effective_period"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{MANUAL_PURCHASE_CYCLE_OVERRIDE}")),
        sa.CheckConstraint(
            "char_length(trim(reason)) > 0",
            name=op.f(f"ck_{MANUAL_PURCHASE_CYCLE_OVERRIDE}_nonblank_reason"),
        ),
        sa.CheckConstraint(
            "kind IN ('exclude', 'restore', 'arrival_date', 'baseline')",
            name=op.f(f"ck_{MANUAL_PURCHASE_CYCLE_OVERRIDE}_kind"),
        ),
    )
    op.create_index(
        "ix_manual_purchase_cycle_override_order_sn",
        MANUAL_PURCHASE_CYCLE_OVERRIDE,
        ["purchase_order_sn"],
    )
    op.create_index(
        "ix_manual_purchase_cycle_override_sku_active",
        MANUAL_PURCHASE_CYCLE_OVERRIDE,
        ["sku", "is_active"],
    )

    op.create_table(
        RULE_PURCHASE_THRESHOLDS,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "rule_key",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'pmc_purchase_thresholds'"),
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("s1_approval_days", sa.Integer(), nullable=False),
        sa.Column("s2_pending_days", sa.Integer(), nullable=False),
        sa.Column("default_cycle_days", sa.Integer(), nullable=False),
        sa.Column("arrival_ratio", sa.Numeric(5, 4), nullable=False),
        sa.Column("auto_exclude_below_days", sa.Integer(), nullable=False),
        sa.Column("sample_window", sa.Integer(), nullable=False),
        sa.Column("min_samples_for_average", sa.Integer(), nullable=False),
        sa.Column("unstable_min_samples", sa.Integer(), nullable=False),
        sa.Column("unstable_range_days", sa.Integer(), nullable=False),
        sa.Column("baseline_evict_at_samples", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f(f"ck_{RULE_PURCHASE_THRESHOLDS}_effective_period"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f(f"ck_{RULE_PURCHASE_THRESHOLDS}_version")),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{RULE_PURCHASE_THRESHOLDS}")),
        sa.CheckConstraint(
            "arrival_ratio > 0 AND arrival_ratio <= 1",
            name=op.f(f"ck_{RULE_PURCHASE_THRESHOLDS}_arrival_ratio"),
        ),
        sa.CheckConstraint(
            "sample_window >= 1", name=op.f(f"ck_{RULE_PURCHASE_THRESHOLDS}_sample_window")
        ),
        sa.UniqueConstraint("rule_key", "version", name="uq_rule_purchase_thresholds_version"),
    )

    op.execute(
        sa.text(
            f"INSERT INTO {RULE_PURCHASE_THRESHOLDS} (id, rule_key, version, s1_approval_days, "
            "s2_pending_days, default_cycle_days, arrival_ratio, auto_exclude_below_days, "
            "sample_window, min_samples_for_average, unstable_min_samples, unstable_range_days, "
            "baseline_evict_at_samples, effective_from, effective_to, is_active, approved_by, "
            "approved_at, change_reason, created_at) VALUES (gen_random_uuid(), :rule_key, "
            ":version, :s1_approval_days, :s2_pending_days, :default_cycle_days, :arrival_ratio, "
            ":auto_exclude_below_days, :sample_window, :min_samples_for_average, "
            ":unstable_min_samples, :unstable_range_days, :baseline_evict_at_samples, "
            ":effective_from, NULL, :is_active, :approved_by, now(), :change_reason, now())"
        ).bindparams(**THRESHOLDS_V1)
    )


def downgrade() -> None:
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
