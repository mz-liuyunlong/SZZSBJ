from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260929_0026_listing_gpt_analysis_links"
down_revision: str | None = "20260928_0025_listing_management_price_fulfillment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_gpt_analysis_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text(), nullable=True),
        sa.Column("keyword_analysis_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("ad_analysis_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("listing_id", name="uq_listing_gpt_analysis_listing"),
    )
    op.create_index(
        "ix_listing_gpt_analysis_item",
        "listing_gpt_analysis_links",
        ["source_account_ref", "store_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_gpt_analysis_item", table_name="listing_gpt_analysis_links")
    op.drop_table("listing_gpt_analysis_links")
