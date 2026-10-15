"""retire legacy RBAC grants after v2 migration

Revision ID: 20261015_0038_retire_legacy_rbac_permissions
Revises: 20261015_0037_rbac_v2
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op
from app.modules.iam.permission_catalog_v2 import LEGACY_PERMISSION_MAPPINGS

revision: str = "20261015_0038_retire_legacy_rbac_permissions"
down_revision: str | Sequence[str] | None = "20261015_0037_rbac_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    legacy_keys = list(LEGACY_PERMISSION_MAPPINGS)
    if not legacy_keys:
        return
    bind = op.get_bind()
    bind.execute(
        text(
            """
            delete from app_role_permissions
            where permission_key = any(:legacy_keys)
            """
        ),
        {"legacy_keys": legacy_keys},
    )
    bind.execute(
        text(
            """
            update app_permissions
            set is_active = false,
                updated_at = now()
            where permission_key = any(:legacy_keys)
            """
        ),
        {"legacy_keys": legacy_keys},
    )


def downgrade() -> None:
    bind = op.get_bind()
    for legacy_key, replacement_keys in LEGACY_PERMISSION_MAPPINGS.items():
        bind.execute(
            text(
                """
                insert into app_role_permissions (role_id, permission_key, created_at)
                select distinct role_id, :legacy_key, now()
                from app_role_permissions
                where permission_key = any(:replacement_keys)
                on conflict do nothing
                """
            ),
            {
                "legacy_key": legacy_key,
                "replacement_keys": list(replacement_keys),
            },
        )
    bind.execute(
        text(
            """
            update app_permissions
            set is_active = true,
                updated_at = now()
            where permission_key = any(:legacy_keys)
            """
        ),
        {"legacy_keys": list(LEGACY_PERMISSION_MAPPINGS)},
    )
