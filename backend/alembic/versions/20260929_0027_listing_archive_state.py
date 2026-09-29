from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260929_0027_listing_archive_state"
down_revision: str | None = "20260929_0026_listing_gpt_analysis_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_archive_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(255), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("listing_id", name="uq_listing_archive_listing"),
    )
    op.create_index(
        "ix_listing_archive_item",
        "listing_archive_states",
        ["source_account_ref", "store_id", "item_id"],
    )
    op.create_index(
        "ix_listing_archive_status",
        "listing_archive_states",
        ["is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_archive_status", table_name="listing_archive_states")
    op.drop_index("ix_listing_archive_item", table_name="listing_archive_states")
    op.drop_table("listing_archive_states")
