"""Register missing IAM permissions without granting roles or altering production sessions.

This is a reviewed, explicit migration only; never execute it on application boot.
"""

from __future__ import annotations
from collections.abc import Sequence
from sqlalchemy import text
from alembic import op
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS

revision: str = "20261031_0069_iam_permission_catalog"
down_revision: str | Sequence[str] | None = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for item in PERMISSION_DEFINITIONS:
        connection.execute(
            text("""
            INSERT INTO app_permissions (
                permission_key, name, group_key, description,
                permission_type, module_key, page_key, action_key, field_key,
                risk_level, sort_order, is_active, created_at, updated_at
            ) VALUES (
                :permission_key, :name, :group_key, :description,
                :permission_type, :module_key, :page_key, :action_key, :field_key,
                :risk_level, :sort_order, true, now(), now()
            )
            ON CONFLICT (permission_key) DO UPDATE SET
                name = EXCLUDED.name, description = EXCLUDED.description,
                is_active = true, updated_at = now()
        """),
            {
                "permission_key": item.permission_key,
                "name": item.name,
                "group_key": item.module_key,
                "description": item.description,
                "permission_type": item.permission_type,
                "module_key": item.module_key,
                "page_key": item.page_key,
                "action_key": item.action_key,
                "field_key": item.field_key,
                "risk_level": item.risk_level,
                "sort_order": item.sort_order,
            },
        )


def downgrade() -> None:
    """Keep permission records and grants intact on downgrade.

    Permission catalog rows can preexist this migration or have active role
    associations. Deleting or deactivating them would silently revoke access.
    Reapplying this migration is idempotent, so preserving them is safe.
    """
    pass
