"""Add append-only global Listing grade rule versions (no rating/backfill)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_0055_listing_grade_rule_versions"
down_revision: str | Sequence[str] | None = (
    "20261022_0054_merge_walmart_identity_and_domestic_packing"
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_listing_grade_rule_versions",
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.CheckConstraint("version > 0", name="listing_grade_rule_positive_version"),
        sa.CheckConstraint(
            "length(btrim(change_reason)) >= 3", name="listing_grade_rule_change_reason"
        ),
    )
    # Keep the IAM permission catalog in sync with the newly gated action.
    op.execute(
        sa.text("""
      INSERT INTO app_permissions
      (permission_key,name,group_key,description,permission_type,module_key,page_key,
       action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
      VALUES
      ('action:products:listing-management:configure-rules',
       '配置Listing评级规则','products','配置全局Listing等级评级参数',
       'action','products','products_listing_management','configure_rules',NULL,
       'high',60,true,now(),now())
      ON CONFLICT(permission_key) DO NOTHING
    """)
    )


def downgrade() -> None:
    # Never destroy rule history that may already have been used for auditing.
    raise RuntimeError("LISTING_RULE_HISTORY_REQUIRES_VERIFIED_BACKUP_RESTORE")
