"""Backfill Approval Workspace page access without broadening WFS review or data scope.

Revision ID: 20261017_0042_approval_rbac_backfill
Revises: 20261016_0041_wfs_rbac_actions
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261017_0042_approval_rbac_backfill"
down_revision: str | Sequence[str] | None = "20261016_0041_wfs_rbac_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_APPROVAL_VIEW = "approvals:workbench:read"
APPROVAL_PAGE_VIEW = "page:data-center:approval-workspace:view"
USER_DATA_SCOPE_ACTION = "action:settings:user-management:configure-data-scope"

NEW_ACTIONS = (
    (
        "action:products:product-management:update-pricing-rules",
        "维护定价规则",
        "update-pricing-rules",
        "high",
        50,
    ),
    (
        "action:products:product-management:view-sync-history",
        "查看同步历史",
        "view-sync-history",
        "normal",
        8,
    ),
    (
        "action:products:product-management:view-raw-lineage",
        "查看数据血缘",
        "view-raw-lineage",
        "high",
        9,
    ),
    (
        "action:products:product-management:view-operation-logs",
        "查看操作日志",
        "view-operation-logs",
        "normal",
        10,
    ),
    (
        "action:pmc:purchase-board:override",
        "维护采购周期覆盖",
        "override",
        "high",
        10,
    ),
)

LEGACY_EQUIVALENT_GRANTS = {
    LEGACY_APPROVAL_VIEW: (APPROVAL_PAGE_VIEW,),
    "products:read": ("page:products:product-management:view",),
    "product_listings:read": ("page:products:product-management:view",),
    "products:sync_history:read": ("action:products:product-management:view-sync-history",),
    "products:raw_lineage:read": ("action:products:product-management:view-raw-lineage",),
    "products:operation_logs:read": ("action:products:product-management:view-operation-logs",),
    "products:cost:read": ("field:products:product-management:purchase-cost",),
    "products:pricing_rules:update": ("action:products:product-management:update-pricing-rules",),
    "pmc:purchase:override": ("action:pmc:purchase-board:override",),
}


def upgrade() -> None:
    bind = op.get_bind()

    # User-level scope editing is deliberately high risk and receives no automatic role grant.
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
                '配置用户数据权限',
                'settings',
                '用户管理：配置用户数据权限',
                'action',
                'settings',
                'settings_user_management',
                'configure_data_scope',
                null,
                'high',
                70,
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
        {"permission_key": USER_DATA_SCOPE_ACTION},
    )

    for permission_key, name, action_key, risk_level, sort_order in NEW_ACTIONS:
        module_key, page_key = (
            ("pmc", "pmc_purchase_board")
            if permission_key.startswith("action:pmc:")
            else ("products", "products_product_management")
        )
        bind.execute(
            text(
                """
                insert into app_permissions (
                    permission_key, name, group_key, description, permission_type,
                    module_key, page_key, action_key, field_key, risk_level,
                    sort_order, is_active, created_at, updated_at
                )
                values (
                    :permission_key, :name, :module_key, :description, 'action',
                    :module_key, :page_key, :action_key, null, :risk_level,
                    :sort_order, true, now(), now()
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
                "module_key": module_key,
                "description": f"{page_key}：{name}",
                "page_key": page_key,
                "action_key": action_key,
                "risk_level": risk_level,
                "sort_order": sort_order,
            },
        )

    # Copy only explicit legacy-equivalent grants. Keep legacy grants for rolling deployment;
    # do not infer archive-review privileges and do not create data-scope rows.
    for legacy_key, canonical_keys in LEGACY_EQUIVALENT_GRANTS.items():
        for canonical_key in canonical_keys:
            bind.execute(
                text(
                    """
                    insert into app_role_permissions (role_id, permission_key, created_at)
                    select legacy.role_id, :canonical_key, now()
                    from app_role_permissions legacy
                    join app_permissions canonical
                      on canonical.permission_key = :canonical_key
                     and canonical.is_active = true
                    where legacy.permission_key = :legacy_key
                    on conflict do nothing
                    """
                ),
                {"legacy_key": legacy_key, "canonical_key": canonical_key},
            )


def downgrade() -> None:
    """Block automatic rollback because copied grants cannot be distinguished safely later."""
    raise RuntimeError(
        "Forward-only RBAC migration: restore from an approved snapshot or use a reviewed "
        "compensating migration; do not delete grants automatically."
    )
