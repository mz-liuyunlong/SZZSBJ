"""Manual Listing lifecycle status and immutable change-history tables.

Never run on the production tunnel without explicit owner authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0073_listing_lifecycle_manual"
down_revision: str | Sequence[str] | None = "20261104_0072_wfs_la_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_listing_lifecycle_manual_states",
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_account_ref", "store_id", "item_id"),
    )
    op.create_table(
        "biz_listing_lifecycle_manual_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.Text()),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_stage", sa.String(64)),
        sa.Column("new_stage", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_listing_lifecycle_manual_hist_identity",
        "biz_listing_lifecycle_manual_history",
        ["source_account_ref", "store_id", "item_id", "changed_at"],
    )
    op.execute(
        text("""
        INSERT INTO app_permissions (
          permission_key, name, group_key, description, permission_type,
          module_key, page_key, action_key, field_key, risk_level,
          sort_order, is_active, created_at, updated_at
        ) VALUES (
          'action:products:listing-management:edit-lifecycle',
          '人工修改Listing生命周期', 'products', '单个及批量修改生命周期',
          'action', 'products', 'products_listing_management',
          'edit_lifecycle', NULL, 'high', 55, TRUE, now(), now()
        ) ON CONFLICT (permission_key) DO NOTHING
    """)
    )


def downgrade() -> None:
    raise RuntimeError("Lifecycle manual history is immutable: destructive downgrade is blocked")
