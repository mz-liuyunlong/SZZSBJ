"""Persist unresolved SEM expense by provider task and CSV row.

Revision ID: 20261109_0083_finance_sem_unallocated_lines
Revises: 20261108_0082_clearance_center
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261109_0083_finance_sem_unallocated_lines"
down_revision = "20261108_0082_clearance_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_finance_unallocated_sem_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_hash", sa.Text()),
        sa.Column("campaign_id", sa.Text()),
        sa.Column("candidate_item_id", sa.Text()),
        sa.Column("spend_amount_usd", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("owner_note", sa.Text()),
        sa.Column("resolved_by", sa.String(128)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source_account_ref",
            "business_date_la",
            "store_id",
            "task_id",
            "row_index",
            name="uq_finance_sem_unallocated_source_line",
        ),
        sa.CheckConstraint(
            "status IN ('pending','investigating','resolved','dismissed')",
            name="ck_finance_sem_unallocated_status",
        ),
    )
    op.create_table(
        "biz_finance_sample_disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=False),
        sa.Column("sample_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("sales_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("sample_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("sales_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("owner_note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source_account_ref",
            "business_date_la",
            "store_id",
            "item_id",
            "msku",
            name="uq_finance_sample_dispute_listing_day",
        ),
        sa.CheckConstraint(
            "status IN ('pending','investigating','resolved','dismissed')",
            name="ck_finance_sample_dispute_status",
        ),
    )
    op.create_index(
        "ix_finance_sample_dispute_current",
        "biz_finance_sample_disputes",
        ["source_account_ref", "business_date_la", "is_current"],
    )
    op.create_index(
        "ix_finance_sem_unallocated_current",
        "biz_finance_unallocated_sem_lines",
        ["source_account_ref", "business_date_la", "is_current"],
    )


def downgrade() -> None:
    # Financial audit history is intentionally non-destructive.
    raise RuntimeError("finance SEM audit ledger has no destructive downgrade")
