"""Durable Listing lifecycle automatic publication history and daily job ledger.

Production execution requires separate owner authorization.  The migration
itself only creates tables; it never updates Listing lifecycle statuses.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0074_listing_lifecycle_auto"
down_revision: str | Sequence[str] | None = "20261104_0073_listing_lifecycle_manual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_listing_lifecycle_auto_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("msku", sa.Text()),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("previous_stage", sa.String(64)),
        sa.Column("new_stage", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("valid_stock_days_30", sa.Integer(), nullable=False),
        sa.Column("consecutive_low_stock_days", sa.Integer(), nullable=False),
        sa.Column("first_positive_date_la", sa.Date(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            "cutoff_date_la",
            name="uq_listing_lifecycle_auto_identity_cutoff",
        ),
        sa.CheckConstraint(
            "valid_stock_days_30 >= 0 AND consecutive_low_stock_days >= 0",
            name="ck_listing_lifecycle_auto_nonnegative",
        ),
    )
    op.create_index(
        "ix_listing_lifecycle_auto_history_lookup",
        "biz_listing_lifecycle_auto_history",
        ["source_account_ref", "store_id", "item_id", "cutoff_date_la"],
    )
    op.create_table(
        "biz_listing_lifecycle_auto_runs",
        sa.Column("schedule_date_cn", sa.Date(), primary_key=True),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "skipped_reasons_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_listing_lifecycle_auto_run_status",
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Immutable lifecycle audit cannot be destructively downgraded")
