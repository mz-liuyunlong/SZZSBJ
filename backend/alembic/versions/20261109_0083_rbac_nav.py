"""Register role-managed navigation pages and sensitive actions without granting roles.

Revision ID: 20261109_0083_rbac_nav
Revises: 20261108_0082_clearance_center
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS

revision: str = "20261109_0083_rbac_nav"
down_revision: str | Sequence[str] | None = "20261108_0082_clearance_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A role grants a permission only through app_role_permissions; this revision adds
# definitions, never grants. Reused navigation keys remain shared as before.
NEW_ACTION_PREFIXES = ("action:finance:", "action:settings:business-config:")


def _registered_definitions():
    return (
        entry
        for entry in PERMISSION_DEFINITIONS
        if entry.permission_type == "page" or entry.permission_key.startswith(NEW_ACTION_PREFIXES)
    )


def upgrade() -> None:
    bind = op.get_bind()
    for definition in _registered_definitions():
        bind.execute(
            text(
                """
                insert into app_permissions (
                    permission_key, name, group_key, description, permission_type,
                    module_key, page_key, action_key, field_key, risk_level,
                    sort_order, is_active, created_at, updated_at
                )
                values (
                    :permission_key, :name, :module_key, :description, :permission_type,
                    :module_key, :page_key, :action_key, :field_key, :risk_level,
                    :sort_order, true, now(), now()
                )
                on conflict (permission_key) do nothing
                """
            ),
            {
                "permission_key": definition.permission_key,
                "name": definition.name,
                "description": definition.description,
                "permission_type": definition.permission_type,
                "module_key": definition.module_key,
                "page_key": definition.page_key,
                "action_key": definition.action_key,
                "field_key": definition.field_key,
                "risk_level": definition.risk_level,
                "sort_order": definition.sort_order,
            },
        )


def downgrade() -> None:
    # Preserve registered permission definitions and any assigned role grants.
    # This non-destructive downgrade allows Alembic to continue to 0082, whose
    # protected clearance history explicitly forbids further rollback.
    pass
