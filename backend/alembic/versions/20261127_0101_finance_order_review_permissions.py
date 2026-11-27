"""结算利润 V3 PR-OR：订单审核页面与动作权限登记（按 #347 RBAC），不建表。

Revision ID: 20261127_0101_finance_order_review_permissions
Revises: 20261127_0100_sku_ad_progress_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261127_0101_finance_order_review_permissions"
down_revision: str | Sequence[str] | None = "20261127_0100_sku_ad_progress_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAGE_KEY = "finance_order_review"
PERMISSIONS = (
    ("page:finance:order-review:view", "page", None, "订单审核", 70060),
    (
        "action:finance:order-review:cost-entry",
        "action",
        "cost-entry",
        "订单审核录成本 / 确认 / 撤销录入",
        70061,
    ),
    ("action:finance:order-review:review1", "action", "review1", "订单审核初审", 70062),
    ("action:finance:order-review:review2", "action", "review2", "订单审核终审", 70063),
    ("action:finance:order-review:recalc", "action", "recalc", "订单审核重算", 70064),
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, kind, action, name, sort in PERMISSIONS:
        bind.execute(
            sa.text(
                """INSERT INTO app_permissions
         (permission_key,name,group_key,description,permission_type,module_key,page_key,
          action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
         VALUES (:key,:name,'finance',:name,:kind,'finance',:page,
          :action,NULL,'normal',:sort,true,now(),now())
         ON CONFLICT(permission_key) DO NOTHING"""
            ),
            {
                "key": key,
                "name": name,
                "kind": kind,
                "action": action,
                "page": PAGE_KEY,
                "sort": sort,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    keys = [key for key, *_ in PERMISSIONS]
    if bind.scalar(
        sa.text("SELECT count(*) FROM app_role_permissions WHERE permission_key = ANY(:keys)"),
        {"keys": keys},
    ):
        raise RuntimeError("rollback blocked: order review permissions are assigned to roles")
    bind.execute(
        sa.text("DELETE FROM app_permissions WHERE permission_key = ANY(:keys)"), {"keys": keys}
    )
