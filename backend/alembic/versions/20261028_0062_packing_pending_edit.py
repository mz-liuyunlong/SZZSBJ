"""Persist automatic pending packing modify drafts before approval."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0062_packing_pending_edit"
down_revision = "20261027_0061_merge_purchase_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_domestic_packing_pending_edits",
        sa.Column("candidate_id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("base_candidate_version", sa.String(64), nullable=False),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("customs", sa.String(16), nullable=False),
        sa.Column("edit_reason", sa.String(500)),
        sa.Column("draft_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "requested_qty BETWEEN 1 AND 1000000",
            name="pending_edit_quantity",
        ),
        sa.CheckConstraint(
            "customs IN ('default','declare','skip')",
            name="pending_edit_customs",
        ),
    )
    op.create_index(
        "ix_ops_domestic_packing_pending_edits_source_account_ref",
        "ops_domestic_packing_pending_edits",
        ["source_account_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ops_domestic_packing_pending_edits_source_account_ref",
        table_name="ops_domestic_packing_pending_edits",
    )
    op.drop_table("ops_domestic_packing_pending_edits")
