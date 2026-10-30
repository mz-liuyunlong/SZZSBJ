"""Persist new-product scoring, workflow and immutable audit events.

Revision ID: 20261030_0070_new_product_workflows
Revises: 20261030_0069_new_product_rbac_catalog
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261030_0070_new_product_workflows"
down_revision = "20261030_0069_new_product_rbac_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_new_workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sku_identity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_market"),
        sa.Column("market_score", sa.Integer()),
        sa.Column("market_reason", sa.Text()),
        sa.Column("purchase_request_qty", sa.Integer()),
        sa.Column("purchase_reason", sa.Text()),
        sa.Column("purchase_review_by", sa.String(128)),
        sa.Column("purchase_review_at", sa.DateTime(timezone=True)),
        sa.Column("purchase_review_note", sa.Text()),
        sa.Column("review_result", sa.String(32)),
        sa.Column("review_reason", sa.Text()),
        sa.Column("review_due_at", sa.Date()),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("score_snapshot_json", JSONB()),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("sku_identity_id", name="uq_product_new_workflows_sku"),
        sa.CheckConstraint("market_score IS NULL OR market_score BETWEEN 0 AND 10", name="ck_new_product_market"),
        sa.CheckConstraint("purchase_request_qty IS NULL OR purchase_request_qty > 0", name="ck_new_product_purchase_qty"),
        sa.CheckConstraint(
            "status IN ('pending_market','scored','pending_purchase','approved_draft','rejected')",
            name="ck_new_product_status",
        ),
        sa.CheckConstraint(
            "review_result IS NULL OR review_result IN ('observe','optimize','success','failure')",
            name="ck_new_product_review",
        ),
    )
    op.create_index(
        "ix_product_new_workflows_account",
        "product_new_workflows",
        ["source_account_ref", "status"],
    )
    op.create_table(
        "product_new_workflow_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_new_workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_json", JSONB()),
        sa.Column("after_json", JSONB(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_product_new_events_workflow",
        "product_new_workflow_events",
        ["workflow_id", "created_at"],
    )
    op.create_table(
        "product_new_rule_versions",
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("rule_json", JSONB(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("product_new_rule_versions")
    op.drop_index("ix_product_new_events_workflow", table_name="product_new_workflow_events")
    op.drop_table("product_new_workflow_events")
    op.drop_index("ix_product_new_workflows_account", table_name="product_new_workflows")
    op.drop_table("product_new_workflows")
