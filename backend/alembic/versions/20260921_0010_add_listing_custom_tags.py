"""add listing custom tags

Revision ID: 20260921_0010_add_listing_custom_tags
Revises: 20260919_0016
Create Date: 2026-09-21 02:50:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0010_add_listing_custom_tags"
down_revision: str | None = "20260919_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_custom_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("name <> ''", name="product_custom_tag_name_not_blank"),
        sa.CheckConstraint("color <> ''", name="product_custom_tag_color_not_blank"),
    )
    op.create_index(
        "ix_product_custom_tags_active_sort",
        "product_custom_tags",
        ["is_active", "sort_order", "name"],
    )

    op.create_table(
        "product_custom_tag_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["product_custom_tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_account_ref",
            "item_id",
            "tag_id",
            name="uq_product_custom_tag_assignment_item_tag",
        ),
        sa.CheckConstraint("source_account_ref <> ''", name="tag_assignment_account_not_blank"),
        sa.CheckConstraint("item_id <> ''", name="tag_assignment_item_not_blank"),
    )
    op.create_index(
        "ix_product_custom_tag_assignments_item",
        "product_custom_tag_assignments",
        ["source_account_ref", "item_id"],
    )
    op.create_index(
        "ix_product_custom_tag_assignments_tag",
        "product_custom_tag_assignments",
        ["tag_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_custom_tag_assignments_tag", table_name="product_custom_tag_assignments"
    )
    op.drop_index(
        "ix_product_custom_tag_assignments_item", table_name="product_custom_tag_assignments"
    )
    op.drop_table("product_custom_tag_assignments")
    op.drop_index("ix_product_custom_tags_active_sort", table_name="product_custom_tags")
    op.drop_table("product_custom_tags")
