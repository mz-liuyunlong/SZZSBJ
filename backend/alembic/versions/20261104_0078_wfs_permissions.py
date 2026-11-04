"""Register the WFS permission definitions (待发货打包单 / 创建货件 / WFS 设置).

The definitions were added to ``app.modules.iam.permission_catalog_v2`` after 0038 had run
on the server, and so far were only registered locally (``scripts/wfs_pending_permissions.py``).
This migration registers them on every database. Rows are copied here (not imported) so the
migration stays frozen. Only ``app_permissions`` changes: no role or user grant is touched;
the administrator grants them in 权限管理. Existing rows are left as they are.
Downgrade removes only rows that no role uses.
"""

from sqlalchemy import text

from alembic import op

revision = "20261104_0078_wfs_permissions"
down_revision = "20261103_0077_wfs_settings"
branch_labels = None
depends_on = None

# permission_key, name, description, type, page_key, action_key, risk, sort_order
ROWS = (
    (
        "page:pmc:wfs:view",
        "WFS",
        "允许进入并查看「WFS」页面",
        "page",
        "pmc_wfs",
        None,
        "normal",
        100030,
    ),
    (
        "page:pmc:wfs-pending-packing:view",
        "待发货打包单",
        "允许进入并查看「待发货打包单」页面",
        "page",
        "pmc_wfs_pending_packing",
        None,
        "normal",
        100031,
    ),
    (
        "page:pmc:wfs-settings:view",
        "WFS设置",
        "允许进入并查看「WFS设置」页面",
        "page",
        "pmc_wfs_settings",
        None,
        "normal",
        100034,
    ),
    (
        "action:pmc:wfs-pending-packing:draft-submit",
        "生成待审批货件草稿",
        "待发货打包单：生成待审批货件草稿",
        "action",
        "pmc_wfs_pending_packing",
        "draft-submit",
        "normal",
        10,
    ),
    (
        "action:pmc:wfs-pending-packing:identity-switch",
        "换店铺或商品链接",
        "待发货打包单：换店铺或商品链接",
        "action",
        "pmc_wfs_pending_packing",
        "identity-switch",
        "normal",
        20,
    ),
    (
        "action:pmc:wfs-pending-packing:create",
        "提交 WFS 创建（自动检查并占用箱子）",
        "待发货打包单：提交 WFS 创建（自动检查并占用箱子）",
        "action",
        "pmc_wfs_pending_packing",
        "create",
        "normal",
        30,
    ),
    (
        "action:pmc:wfs-pending-packing:approve",
        "人工书面批准 WFS 创建（调用 Walmart）",
        "待发货打包单：人工书面批准 WFS 创建（调用 Walmart），失败后重试也用此权限",
        "action",
        "pmc_wfs_pending_packing",
        "approve",
        "high",
        35,
    ),
    (
        "action:pmc:wfs-pending-packing:preview",
        "按需探测分仓",
        "待发货打包单：按需探测分仓",
        "action",
        "pmc_wfs_pending_packing",
        "preview",
        "normal",
        40,
    ),
    (
        "action:pmc:wfs-pending-packing:reconcile",
        "核实创建结果",
        "待发货打包单：核实创建结果",
        "action",
        "pmc_wfs_pending_packing",
        "reconcile",
        "normal",
        50,
    ),
    (
        "action:pmc:wfs-pending-packing:label-retry",
        "补取箱唛",
        "待发货打包单：补取箱唛",
        "action",
        "pmc_wfs_pending_packing",
        "label-retry",
        "normal",
        60,
    ),
    (
        "action:pmc:wfs-settings:manage",
        "维护 WFS 设置（规则版本 / 地区 / 默认值）",
        "WFS设置：维护 WFS 设置（规则版本 / 地区 / 默认值）",
        "action",
        "pmc_wfs_settings",
        "manage",
        "normal",
        10,
    ),
)
KEYS = tuple(row[0] for row in ROWS)


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, description, kind, page_key, action_key, risk, sort_order in ROWS:
        bind.execute(
            text(
                """
                insert into app_permissions (
                    permission_key, name, group_key, description, permission_type,
                    module_key, page_key, action_key, field_key, risk_level,
                    sort_order, is_active, created_at, updated_at
                )
                values (
                    :key, :name, 'pmc', :description, :kind,
                    'pmc', :page_key, :action_key, null, :risk,
                    :sort_order, true, now(), now()
                )
                on conflict (permission_key) do nothing
                """
            ),
            {
                "key": key,
                "name": name,
                "description": description,
                "kind": kind,
                "page_key": page_key,
                "action_key": action_key,
                "risk": risk,
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for key in KEYS:
        bind.execute(
            text(
                """
                delete from app_permissions p
                where p.permission_key = :key
                  and not exists (
                    select 1 from app_role_permissions r where r.permission_key = p.permission_key
                  )
                """
            ),
            {"key": key},
        )
