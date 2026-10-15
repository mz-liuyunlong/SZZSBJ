"""map formal WFS Case permissions into page-specific RBAC actions

Revision ID: 20261015_0040_wfs_rbac_actions
Revises: 20261015_0039_restrict_default_data_scopes
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261015_0040_wfs_rbac_actions"
down_revision: str | Sequence[str] | None = "20261015_0039_restrict_default_data_scopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WFS_ACTIONS = (
    (
        "action:warehouse:wfs-fee-alert:follow",
        "跟进WFS Case",
        "follow",
        "编辑 WFS Case 跟进记录",
        "normal",
        10,
    ),
    (
        "action:warehouse:wfs-fee-alert:archive-request",
        "申请归档WFS Case",
        "archive_request",
        "提交 WFS Case 归档申请",
        "high",
        20,
    ),
    (
        "action:warehouse:wfs-fee-alert:archive-review",
        "审核归档WFS Case",
        "archive_review",
        "审核 WFS Case 归档申请",
        "high",
        30,
    ),
    (
        "action:warehouse:wfs-fee-alert:mark-recovered",
        "确认WFS Case追回",
        "mark_recovered",
        "确认 WFS Case 追回金额",
        "high",
        40,
    ),
    (
        "action:warehouse:wfs-fee-alert:sync-legacy",
        "同步历史WFS Case",
        "sync_legacy",
        "预检、比对并同步历史 WFS Case",
        "high",
        50,
    ),
)

LEGACY_ACTION_MAPPINGS = {
    "warehouse:wfs-fee-alert:write": (
        "action:warehouse:wfs-fee-alert:follow",
        "action:warehouse:wfs-fee-alert:archive-request",
    ),
    "warehouse:wfs-fee-alert:review": ("action:warehouse:wfs-fee-alert:archive-review",),
    "warehouse:wfs-fee-alert:recover": ("action:warehouse:wfs-fee-alert:mark-recovered",),
    "warehouse:wfs-fee-alert:sync": ("action:warehouse:wfs-fee-alert:sync-legacy",),
}


def upgrade() -> None:
    bind = op.get_bind()
    for permission_key, name, action_key, description, risk_level, sort_order in WFS_ACTIONS:
        bind.execute(
            text(
                """
                insert into app_permissions (
                    permission_key,
                    name,
                    group_key,
                    description,
                    permission_type,
                    module_key,
                    page_key,
                    action_key,
                    field_key,
                    risk_level,
                    sort_order,
                    is_active,
                    created_at,
                    updated_at
                )
                values (
                    :permission_key,
                    :name,
                    'warehouse',
                    :description,
                    'action',
                    'warehouse',
                    'warehouse_wfs_fee_alert',
                    :action_key,
                    null,
                    :risk_level,
                    :sort_order,
                    true,
                    now(),
                    now()
                )
                on conflict (permission_key) do update set
                    name = excluded.name,
                    group_key = excluded.group_key,
                    description = excluded.description,
                    permission_type = excluded.permission_type,
                    module_key = excluded.module_key,
                    page_key = excluded.page_key,
                    action_key = excluded.action_key,
                    field_key = excluded.field_key,
                    risk_level = excluded.risk_level,
                    sort_order = excluded.sort_order,
                    is_active = true,
                    updated_at = now()
                """
            ),
            {
                "permission_key": permission_key,
                "name": name,
                "description": description,
                "action_key": action_key,
                "risk_level": risk_level,
                "sort_order": sort_order,
            },
        )

    for legacy_key, replacement_keys in LEGACY_ACTION_MAPPINGS.items():
        for replacement_key in replacement_keys:
            bind.execute(
                text(
                    """
                    insert into app_role_permissions (role_id, permission_key, created_at)
                    select role_id, :replacement_key, now()
                    from app_role_permissions
                    where permission_key = :legacy_key
                    on conflict do nothing
                    """
                ),
                {
                    "legacy_key": legacy_key,
                    "replacement_key": replacement_key,
                },
            )

    legacy_keys = list(LEGACY_ACTION_MAPPINGS)
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
    for legacy_key, replacement_keys in LEGACY_ACTION_MAPPINGS.items():
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
        {"legacy_keys": list(LEGACY_ACTION_MAPPINGS)},
    )
    bind.execute(
        text(
            """
            delete from app_permissions
            where permission_key = any(:permission_keys)
            """
        ),
        {"permission_keys": [item[0] for item in WFS_ACTIONS]},
    )
