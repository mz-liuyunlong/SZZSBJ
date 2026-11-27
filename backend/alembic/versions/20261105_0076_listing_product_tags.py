"""Persist Product Management tags separately from Listing custom tags.

Revision ID: 20261105_0076_listing_product_tags
Revises: 20261105_0075_listing_lifecycle_auto
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261105_0076_listing_product_tags"
down_revision = "20261105_0075_listing_lifecycle_auto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mart_listing_management_current",
        sa.Column(
            "product_tags_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "mart_listing_management_current",
        sa.Column(
            "product_tags_match_status", sa.String(32), nullable=False, server_default="pending"
        ),
    )
    op.create_check_constraint(
        "ck_listing_product_tags_match_status",
        "mart_listing_management_current",
        "product_tags_match_status IN ('pending', 'matched', 'unmatched', 'ambiguous', 'no_sku')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_listing_product_tags_match_status", "mart_listing_management_current", type_="check"
    )
    op.drop_column("mart_listing_management_current", "product_tags_match_status")
    op.drop_column("mart_listing_management_current", "product_tags_json")
