"""Register current route grants without revoking any role memberships.

Revision ID: 20261115_0092_role_page_catalog_alignment
Revises: 20261113_0091_finance_wfs_fee_reports
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261115_0092_role_page_catalog_alignment"
down_revision: str | Sequence[str] | None = "20261113_0091_finance_wfs_fee_reports"
branch_labels = None
depends_on = None

# FX rates is deliberately omitted: only super-admin (*) may access it.
# The pre-existing WFS fees key is kept, not regranted.
NEW_PAGES = (
    ("products", "products_clearance_center", "clearance-center", "清货中心", 15),
    ("products", "products_launch_tracking", "launch-tracking", "打品跟踪", 45),
    ("finance", "finance_settlement_profit", "settlement-profit", "结算利润", 25),
    ("finance", "finance_wfs_fees", "wfs-fees", "WFS 费用明细", 45),
    ("finance", "finance_balance_sheet", "balance-sheet", "资产负债表", 75),
    ("finance", "finance_cash_flow", "cash-flow", "资金流水", 80),
    ("finance", "finance_cost_exception", "cost-exception", "成本异常处理", 85),
    ("finance", "finance_settings", "settings", "口径与设置", 90),
    ("finance", "finance_data_import", "data-import", "数据导入", 95),
    ("pmc", "pmc_logistics", "logistics", "物流", 30),
    ("data_center", "data_center_walmart_remote", "walmart-remote", "沃尔玛采集", 25),
)


def upgrade() -> None:
    bind = op.get_bind()
    for module_key, page_key, slug, name, sort_order in NEW_PAGES:
        bind.execute(
            text("""
            INSERT INTO app_permissions (
                permission_key, name, group_key, description, permission_type,
                module_key, page_key, action_key, field_key, risk_level,
                sort_order, is_active, created_at, updated_at
            ) VALUES (
                :permission_key, :name, :module_key, :description, 'page',
                :module_key, :page_key, NULL, NULL, 'normal',
                :sort_order, true, now(), now()
            ) ON CONFLICT (permission_key) DO NOTHING
        """),
            {
                "permission_key": f"page:{module_key.replace('_', '-')}:{slug}:view",
                "name": name,
                "module_key": module_key,
                "page_key": page_key,
                "description": f"允许进入并查看「{name}」页面",
                "sort_order": sort_order,
            },
        )

    # Copy existing effective access once, then let the two pages be toggled independently.
    # Do not revoke, delete, or broaden any existing role grants.
    for old_key, new_key in (
        ("page:products:product-management:view", "page:products:clearance-center:view"),
        ("page:products:new-product-analysis:view", "page:products:launch-tracking:view"),
    ):
        bind.execute(
            text("""
            INSERT INTO app_role_permissions (role_id, permission_key, created_at)
            SELECT old_grant.role_id, :new_key, now()
            FROM app_role_permissions AS old_grant
            JOIN app_permissions AS target
              ON target.permission_key = :new_key AND target.is_active = true
            WHERE old_grant.permission_key = :old_key
            ON CONFLICT DO NOTHING
        """),
            {"old_key": old_key, "new_key": new_key},
        )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only permission catalog migration: do not revoke role grants automatically"
    )
