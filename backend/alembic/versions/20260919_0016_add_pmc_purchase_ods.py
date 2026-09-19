"""Add PMC purchase board ODS tables (purchase plans, purchase orders, receipt orders).

Revision ID: 20260919_0016
Revises: 20260918_0015
Create Date: 2026-09-19

Gate 2 / PR-B of PRPs/pmc-purchase-board.md. Append-only ODS storage; every row keeps
the full provider record in ``payload_json``. Running this against production still
requires PRODUCTION_MIGRATIONS_AUTHORIZED per the runbook.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0016"
down_revision: str | Sequence[str] | None = "20260918_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVIDER_TIME = sa.String(32)
PROVIDER_ID = sa.String(64)
MONEY = sa.Numeric(18, 4)

PLANS = "ods_lingxing_purchase_plans"
ORDERS = "ods_lingxing_purchase_orders"
ORDER_ITEMS = "ods_lingxing_purchase_order_items"
RECEIPTS = "ods_lingxing_receipt_orders"
RECEIPT_ITEMS = "ods_lingxing_receipt_order_items"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _governance_columns() -> list[sa.Column[object]]:
    return [
        _uuid("id"),
        _uuid("run_id"),
        _uuid("raw_request_ref_id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("source_item_ordinal", sa.Integer(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _governance_constraints(table: str) -> list[sa.schema.SchemaItem]:
    return [
        sa.CheckConstraint(
            "source_item_ordinal >= 0", name=op.f(f"ck_{table}_source_item_ordinal")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _nonblank(table: str, column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"char_length(trim({column})) > 0", name=op.f(f"ck_{table}_{name}"))


def upgrade() -> None:
    op.create_table(
        PLANS,
        *_governance_columns(),
        sa.Column("plan_sn", PROVIDER_ID, nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("status_text", sa.String(64), nullable=True),
        sa.Column("create_time", PROVIDER_TIME, nullable=True),
        sa.Column("expect_arrive_time", PROVIDER_TIME, nullable=True),
        sa.Column("sid", PROVIDER_ID, nullable=True),
        sa.Column("seller_name", sa.String(255), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_id", PROVIDER_ID, nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("quantity_plan", sa.Integer(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("plan_remark", sa.Text(), nullable=True),
        sa.Column("purchaser_id", PROVIDER_ID, nullable=True),
        sa.Column("purchaser_name", sa.String(255), nullable=True),
        sa.Column("is_aux", sa.Integer(), nullable=True),
        sa.Column("is_combo", sa.Integer(), nullable=True),
        sa.Column("wid", PROVIDER_ID, nullable=True),
        sa.Column("warehouse_name", sa.String(255), nullable=True),
        sa.Column("ppg_sn", PROVIDER_ID, nullable=True),
        *_governance_constraints(PLANS),
        _nonblank(PLANS, "plan_sn", "nonblank_plan_sn"),
        sa.UniqueConstraint(
            "raw_request_ref_id", "source_item_ordinal", name="uq_ods_purchase_plan_ref_ordinal"
        ),
        sa.UniqueConstraint(
            "run_id", "source_account_ref", "plan_sn", name="uq_ods_purchase_plan_run_sn"
        ),
    )

    op.create_table(
        ORDERS,
        *_governance_columns(),
        sa.Column("order_sn", PROVIDER_ID, nullable=False),
        sa.Column("custom_order_sn", sa.String(255), nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("status_shipped", sa.Integer(), nullable=True),
        sa.Column("purchase_type", sa.Integer(), nullable=True),
        sa.Column("order_time", PROVIDER_TIME, nullable=True),
        sa.Column("create_time", PROVIDER_TIME, nullable=True),
        sa.Column("auditor_time", PROVIDER_TIME, nullable=True),
        sa.Column("quantity_total", sa.Integer(), nullable=True),
        sa.Column("quantity_receive", sa.Integer(), nullable=True),
        sa.Column("quantity_real", sa.Integer(), nullable=True),
        sa.Column("amount_total", MONEY, nullable=True),
        sa.Column("purchase_currency", sa.String(16), nullable=True),
        sa.Column("purchase_rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("shipping_price", MONEY, nullable=True),
        sa.Column("other_fee", MONEY, nullable=True),
        sa.Column("purchaser_id", PROVIDER_ID, nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        *_governance_constraints(ORDERS),
        _nonblank(ORDERS, "order_sn", "nonblank_order_sn"),
        sa.CheckConstraint("item_count >= 0", name=op.f(f"ck_{ORDERS}_item_count")),
        sa.UniqueConstraint(
            "raw_request_ref_id", "source_item_ordinal", name="uq_ods_purchase_order_ref_ordinal"
        ),
        sa.UniqueConstraint(
            "run_id", "source_account_ref", "order_sn", name="uq_ods_purchase_order_run_sn"
        ),
    )

    op.create_table(
        ORDER_ITEMS,
        *_governance_columns(),
        sa.Column("order_sn", PROVIDER_ID, nullable=False),
        sa.Column("item_id", PROVIDER_ID, nullable=False),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("plan_sn", PROVIDER_ID, nullable=True),
        sa.Column("sid", PROVIDER_ID, nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_id", PROVIDER_ID, nullable=True),
        sa.Column("fnsku", sa.String(64), nullable=True),
        sa.Column("quantity_plan", sa.Integer(), nullable=True),
        sa.Column("quantity_real", sa.Integer(), nullable=True),
        sa.Column("quantity_receive", sa.Integer(), nullable=True),
        sa.Column("quantity_qc", sa.Integer(), nullable=True),
        sa.Column("price", MONEY, nullable=True),
        sa.Column("amount", MONEY, nullable=True),
        sa.Column("quantity_per_case", sa.Integer(), nullable=True),
        sa.Column("cases_num", sa.Integer(), nullable=True),
        sa.Column("expect_arrive_time", PROVIDER_TIME, nullable=True),
        sa.Column("wid", PROVIDER_ID, nullable=True),
        sa.Column("is_delete", sa.Integer(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        *_governance_constraints(ORDER_ITEMS),
        _nonblank(ORDER_ITEMS, "order_sn", "nonblank_order_sn"),
        _nonblank(ORDER_ITEMS, "item_id", "nonblank_item_id"),
        sa.CheckConstraint("line_ordinal >= 0", name=op.f(f"ck_{ORDER_ITEMS}_line_ordinal")),
        sa.UniqueConstraint(
            "raw_request_ref_id",
            "source_item_ordinal",
            "line_ordinal",
            name="uq_ods_purchase_order_item_ref_line",
        ),
        sa.UniqueConstraint(
            "run_id",
            "source_account_ref",
            "order_sn",
            "item_id",
            name="uq_ods_purchase_order_item_run_key",
        ),
    )

    op.create_table(
        RECEIPTS,
        *_governance_columns(),
        sa.Column("order_sn", PROVIDER_ID, nullable=False),
        sa.Column("business_order_sn", PROVIDER_ID, nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("order_type", sa.Integer(), nullable=True),
        sa.Column("qc_type", sa.Integer(), nullable=True),
        sa.Column("receive_time", PROVIDER_TIME, nullable=True),
        sa.Column("expect_arrival_time", PROVIDER_TIME, nullable=True),
        sa.Column("create_time", PROVIDER_TIME, nullable=True),
        sa.Column("update_time", PROVIDER_TIME, nullable=True),
        sa.Column("wid", PROVIDER_ID, nullable=True),
        sa.Column("inbound_order_sns", postgresql.JSONB(), nullable=True),
        sa.Column("supplier_id", PROVIDER_ID, nullable=True),
        sa.Column("logistics_company", sa.String(255), nullable=True),
        sa.Column("logistics_order_no", sa.String(255), nullable=True),
        sa.Column("shipping_cost", MONEY, nullable=True),
        sa.Column("shipping_currency", sa.String(16), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        *_governance_constraints(RECEIPTS),
        _nonblank(RECEIPTS, "order_sn", "nonblank_order_sn"),
        sa.CheckConstraint("item_count >= 0", name=op.f(f"ck_{RECEIPTS}_item_count")),
        sa.UniqueConstraint(
            "raw_request_ref_id", "source_item_ordinal", name="uq_ods_receipt_order_ref_ordinal"
        ),
        sa.UniqueConstraint(
            "run_id", "source_account_ref", "order_sn", name="uq_ods_receipt_order_run_sn"
        ),
    )

    op.create_table(
        RECEIPT_ITEMS,
        *_governance_columns(),
        sa.Column("receipt_order_sn", PROVIDER_ID, nullable=False),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("order_item_id", PROVIDER_ID, nullable=True),
        sa.Column("item_id", PROVIDER_ID, nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("fnsku", sa.String(64), nullable=True),
        sa.Column("seller_id", PROVIDER_ID, nullable=True),
        sa.Column("notice_num_total", sa.Integer(), nullable=True),
        sa.Column("product_receive_num", sa.Integer(), nullable=True),
        sa.Column("quantity_qc_prepare", sa.Integer(), nullable=True),
        sa.Column("quantity_qc_already", sa.Integer(), nullable=True),
        sa.Column("quality_examine_status", sa.Integer(), nullable=True),
        sa.Column("qc_sn", PROVIDER_ID, nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        *_governance_constraints(RECEIPT_ITEMS),
        _nonblank(RECEIPT_ITEMS, "receipt_order_sn", "nonblank_receipt_sn"),
        sa.CheckConstraint("line_ordinal >= 0", name=op.f(f"ck_{RECEIPT_ITEMS}_line_ordinal")),
        sa.UniqueConstraint(
            "raw_request_ref_id",
            "source_item_ordinal",
            "line_ordinal",
            name="uq_ods_receipt_order_item_ref_line",
        ),
        sa.UniqueConstraint(
            "run_id",
            "source_account_ref",
            "receipt_order_sn",
            "line_ordinal",
            name="uq_ods_receipt_order_item_run_line",
        ),
    )

    # Lookup paths the Gate 3 refresh and quality checks will use.
    op.create_index(op.f("ix_ods_purchase_plans_plan_sn"), PLANS, ["plan_sn"])
    op.create_index(op.f("ix_ods_purchase_orders_order_sn"), ORDERS, ["order_sn"])
    op.create_index(op.f("ix_ods_purchase_order_items_order_sn"), ORDER_ITEMS, ["order_sn"])
    op.create_index(op.f("ix_ods_purchase_order_items_item_id"), ORDER_ITEMS, ["item_id"])
    op.create_index(
        op.f("ix_ods_receipt_orders_business_order_sn"), RECEIPTS, ["business_order_sn"]
    )
    op.create_index(
        op.f("ix_ods_receipt_order_items_order_item_id"), RECEIPT_ITEMS, ["order_item_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ods_receipt_order_items_order_item_id"), table_name=RECEIPT_ITEMS)
    op.drop_index(op.f("ix_ods_receipt_orders_business_order_sn"), table_name=RECEIPTS)
    op.drop_index(op.f("ix_ods_purchase_order_items_item_id"), table_name=ORDER_ITEMS)
    op.drop_index(op.f("ix_ods_purchase_order_items_order_sn"), table_name=ORDER_ITEMS)
    op.drop_index(op.f("ix_ods_purchase_orders_order_sn"), table_name=ORDERS)
    op.drop_index(op.f("ix_ods_purchase_plans_plan_sn"), table_name=PLANS)
    op.drop_table(RECEIPT_ITEMS)
    op.drop_table(RECEIPTS)
    op.drop_table(ORDER_ITEMS)
    op.drop_table(ORDERS)
    op.drop_table(PLANS)
