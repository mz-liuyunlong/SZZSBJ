"""Account-scoped score correction approval and immutable decision history.

Revision ID: 20261104_0075_np_corrections
Revises: 20261104_0074_np_plans
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "20261104_0075_np_corrections"
down_revision = "20261104_0074_np_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_new_score_corrections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
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
        sa.Column("dimension", sa.String(16), nullable=False),
        sa.Column("from_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("requested_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("review_note", sa.Text()),
        sa.Column("evidence_json", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "dimension IN ('order','ads','profit','trust')",
            name="ck_np_correction_dimension",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_np_correction_status",
        ),
        sa.CheckConstraint(
            "from_score BETWEEN 0 AND 10 AND requested_score BETWEEN 0 AND 10",
            name="ck_np_correction_score_bounds",
        ),
    )
    op.create_index(
        "ix_np_correction_account",
        "product_new_score_corrections",
        ["source_account_ref", "created_at"],
    )
    op.create_index(
        "uq_np_correction_pending",
        "product_new_score_corrections",
        ["sku_identity_id", "dimension"],
        unique=True,
        postgresql_where=text("status = 'pending'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(text("SELECT count(*) FROM product_new_score_corrections")).scalar_one()
    if count:
        raise RuntimeError("NP_SCORE_CORRECTION_DOWNGRADE_BLOCKED_EXISTING_HISTORY")
    op.drop_index("uq_np_correction_pending", table_name="product_new_score_corrections")
    op.drop_index("ix_np_correction_account", table_name="product_new_score_corrections")
    op.drop_table("product_new_score_corrections")
