"""restrict default RBAC data scopes to the administrator role

Revision ID: 20261015_0038_restrict_default_data_scopes
Revises: 20261015_0037_retire_legacy_rbac_permissions
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261015_0038_restrict_default_data_scopes"
down_revision: str | Sequence[str] | None = "20261015_0037_retire_legacy_rbac_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Fail closed for non-administrator roles until an explicit scope is configured."""
    op.get_bind().execute(
        text(
            """
            delete from app_role_data_scopes scopes
            using app_roles roles
            where scopes.role_id = roles.id
              and roles.role_key <> 'admin'
              and scopes.scope_type = 'source_account'
              and scopes.scope_value = '*'
            """
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        text(
            """
            insert into app_role_data_scopes (
                role_id,
                scope_type,
                scope_value,
                created_at
            )
            select id, 'source_account', '*', now()
            from app_roles
            on conflict do nothing
            """
        )
    )
