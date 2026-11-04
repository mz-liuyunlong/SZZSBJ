"""Independent new-product approval plan persistence (not procurement execution).

Revision ID: 20261104_0074_np_plans
Revises: 20261104_0073_new_product_workflows
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "20261104_0074_np_plans"
down_revision = "20261104_0073_new_product_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_new_purchase_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_number", sa.String(64), nullable=False),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_new_workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sku_identity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="approved"),
        sa.Column(
            "execution_status",
            sa.String(32),
            nullable=False,
            server_default="not_executed",
        ),
        sa.Column("market_score", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_workflow_version", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=False),
        sa.Column("snapshot_json", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workflow_id", name="uq_new_purchase_plan_workflow"),
        sa.UniqueConstraint("sku_identity_id", name="uq_new_purchase_plan_sku"),
        sa.UniqueConstraint("plan_number", name="uq_new_purchase_plan_number"),
        sa.CheckConstraint("quantity > 0", name="ck_new_purchase_plan_qty"),
        sa.CheckConstraint("status = 'approved'", name="ck_new_purchase_plan_status"),
        sa.CheckConstraint(
            "execution_status = 'not_executed'",
            name="ck_new_purchase_plan_not_executed",
        ),
    )
    op.create_index(
        "ix_new_purchase_plan_account_created",
        "product_new_purchase_plans",
        ["source_account_ref", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    total = bind.execute(text("SELECT count(*) FROM product_new_purchase_plans")).scalar_one()
    if total:
        raise RuntimeError("NEW_PRODUCT_PLAN_DOWNGRADE_BLOCKED_EXISTING_PLANS")
    op.drop_index(
        "ix_new_purchase_plan_account_created",
        table_name="product_new_purchase_plans",
    )
    op.drop_table("product_new_purchase_plans")
