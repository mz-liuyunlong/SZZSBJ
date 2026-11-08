"""Register new navigation page permissions without granting any role.

Revision ID: 20261109_0083_rbac_nav
Revises: 20261108_0082_clearance_center
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261109_0083_rbac_nav"
down_revision: str | Sequence[str] | None = "20261108_0082_clearance_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Four finance menu entries deliberately share the cash-flow grant.
# Do not register the FX-rate page, which is super-admin-only.
NEW_PAGE_ROWS: tuple[tuple[str, str, str, int, int], ...] = (
    ("finance", "settlement_profit", "结算利润", 70, 25),
    ("finance", "balance_sheet", "资产负债表", 70, 75),
    ("finance", "cash_flow", "资金流水（四个菜单共用）", 70, 80),
    ("finance", "cost_exception", "成本异常处理", 70, 90),
    ("finance", "settings", "口径与设置", 70, 100),
    ("finance", "data_import", "数据导入", 70, 110),
    ("pmc", "logistics", "物流", 100, 15),
    ("data_center", "walmart_remote", "沃尔玛采集", 120, 55),
)


def _permission_key(module_key: str, page_key: str) -> str:
    return f"page:{module_key.replace('_', '-')}:{page_key.replace('_', '-')}:view"


def upgrade() -> None:
    bind = op.get_bind()
    for module_key, page_key, title, module_order, page_order in NEW_PAGE_ROWS:
        bind.execute(
            text(
                """
                insert into app_permissions (
                    permission_key, name, group_key, description, permission_type,
                    module_key, page_key, action_key, field_key, risk_level,
                    sort_order, is_active, created_at, updated_at
                )
                values (
                    :permission_key, :name, :module_key, :description, 'page',
                    :module_key, :page_key, null, null, 'normal',
                    :sort_order, true, now(), now()
                )
                on conflict (permission_key) do nothing
                """
            ),
            {
                "permission_key": _permission_key(module_key, page_key),
                "name": title,
                "module_key": module_key,
                "page_key": f"{module_key}_{page_key}",
                "description": f"允许进入并查看「{title}」页面",
                "sort_order": module_order * 1000 + page_order,
            },
        )


def downgrade() -> None:
    keys = [_permission_key(module, page) for module, page, *_ in NEW_PAGE_ROWS]
    bind = op.get_bind()
    assigned_count = bind.execute(
        text(
            """
            select count(*)
            from app_role_permissions
            where permission_key = any(:permission_keys)
            """
        ),
        {"permission_keys": keys},
    ).scalar_one()
    if assigned_count:
        raise RuntimeError(
            "Cannot remove role-navigation permissions while assigned to roles; "
            "review grants and use an approved compensating migration."
        )
    bind.execute(
        text("delete from app_permissions where permission_key = any(:permission_keys)"),
        {"permission_keys": keys},
    )
