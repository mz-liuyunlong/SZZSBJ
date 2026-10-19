"""Add canonical Walmart order-line identity and conflict audit.

Revision ID: 20261020_0047_walmart_order_identity_guard
Revises: 20261019_0046_operation_logs

Existing rows intentionally remain non-current. The application adopts one
existing row per source identity during a later provider observation; this
migration never deletes, merges, or backfills historical order data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261020_0047_walmart_order_identity_guard"
down_revision: str | Sequence[str] | None = "20261019_0046_operation_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fact_walmart_order_items",
        sa.Column("canonical_identity_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "fact_walmart_order_items",
        sa.Column(
            "is_identity_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_fact_walmart_order_items_canonical_identity_hash_sha256",
        "fact_walmart_order_items",
        "canonical_identity_hash IS NULL OR canonical_identity_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_fact_walmart_order_items_canonical_identity_current_complete",
        "fact_walmart_order_items",
        "is_identity_current = false OR ("
        "canonical_identity_hash IS NOT NULL AND "
        "nullif(btrim(source_account_ref), '') IS NOT NULL AND "
        "nullif(btrim(store_id), '') IS NOT NULL AND "
        "nullif(btrim(source_order_id), '') IS NOT NULL AND "
        "nullif(btrim(source_order_line_id), '') IS NOT NULL)",
    )
    op.create_index(
        "uq_fact_walmart_order_items_current_identity",
        "fact_walmart_order_items",
        ["canonical_identity_hash"],
        unique=True,
        postgresql_where=sa.text("is_identity_current = true"),
    )

    op.create_table(
        "audit_walmart_order_item_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("source_order_id", sa.String(128), nullable=False),
        sa.Column("source_order_line_id", sa.String(128), nullable=False),
        sa.Column("prior_fact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canonical_fact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prior_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("observed_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("differing_fields_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "resolution_status",
            sa.String(32),
            nullable=False,
            server_default="observed",
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "char_length(canonical_identity_hash) = 64",
            name="ck_walmart_order_conflict_identity_hash",
        ),
        sa.CheckConstraint(
            "char_length(prior_snapshot_hash) = 64",
            name="ck_walmart_order_conflict_prior_hash",
        ),
        sa.CheckConstraint(
            "char_length(observed_snapshot_hash) = 64",
            name="ck_walmart_order_conflict_observed_hash",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('observed', 'owner_reviewed', 'superseded')",
            name="ck_walmart_order_conflict_status",
        ),
        sa.ForeignKeyConstraint(
            ["prior_fact_id"],
            ["fact_walmart_order_items.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_fact_id"],
            ["fact_walmart_order_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_identity_hash",
            "prior_snapshot_hash",
            "observed_snapshot_hash",
            name="uq_audit_walmart_order_item_conflicts_canonical_identity_hash",
        ),
    )
    op.create_index(
        "ix_audit_walmart_order_item_conflicts_identity_observed",
        "audit_walmart_order_item_conflicts",
        ["canonical_identity_hash", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_walmart_order_item_conflicts_identity_observed",
        table_name="audit_walmart_order_item_conflicts",
    )
    op.drop_table("audit_walmart_order_item_conflicts")
    op.drop_index(
        "uq_fact_walmart_order_items_current_identity",
        table_name="fact_walmart_order_items",
    )
    op.drop_constraint(
        "ck_fact_walmart_order_items_canonical_identity_current_complete",
        "fact_walmart_order_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_fact_walmart_order_items_canonical_identity_hash_sha256",
        "fact_walmart_order_items",
        type_="check",
    )
    op.drop_column("fact_walmart_order_items", "is_identity_current")
    op.drop_column("fact_walmart_order_items", "canonical_identity_hash")
