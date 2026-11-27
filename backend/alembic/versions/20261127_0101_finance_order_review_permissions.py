"""结算利润 V3 PR-OR：订单审核页面与动作权限登记（按 #347 RBAC）+ 两个幂等键列。

- manual_settlement_review_actions.idempotency_key（批量审核请求的 Idempotency-Key）
- manual_settlement_cost_entries.revoke_idempotency_key（撤销录入请求的 Idempotency-Key）
- manual_settlement_cost_entries.platform_order_no + 两条范围约束改为三种范围
  （MSKU × 平台订单号：自发货订单、流水没覆盖的差额段；#373 P1）

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


REVIEW_ACTIONS = "manual_settlement_review_actions"
COST_ENTRIES = "manual_settlement_cost_entries"

OLD_ONE_SCOPE = "(shipping_list_code IS NULL) <> (outbound_order_no IS NULL)"
OLD_SCOPE_REF_MATCHES = (
    "scope_ref = CASE WHEN shipping_list_code IS NOT NULL "
    "THEN 'shipping:' || shipping_list_code ELSE 'outbound:' || outbound_order_no END"
)
NEW_ONE_SCOPE = "num_nonnulls(shipping_list_code, outbound_order_no, platform_order_no) = 1"
NEW_SCOPE_REF_MATCHES = (
    "scope_ref = CASE WHEN shipping_list_code IS NOT NULL "
    "THEN 'shipping:' || shipping_list_code "
    "WHEN outbound_order_no IS NOT NULL THEN 'outbound:' || outbound_order_no "
    "ELSE 'order:' || platform_order_no END"
)


def _replace_scope_checks(one_scope: str, scope_ref_matches: str) -> None:
    for name in ("one_scope", "scope_ref_matches"):
        op.drop_constraint(op.f(name), COST_ENTRIES, type_="check")
    op.create_check_constraint(op.f("one_scope"), COST_ENTRIES, one_scope)
    op.create_check_constraint(op.f("scope_ref_matches"), COST_ENTRIES, scope_ref_matches)


def upgrade() -> None:
    op.add_column(REVIEW_ACTIONS, sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index("ix_manual_settlement_review_idem", REVIEW_ACTIONS, ["idempotency_key"])
    op.add_column(COST_ENTRIES, sa.Column("revoke_idempotency_key", sa.String(128), nullable=True))
    op.add_column(COST_ENTRIES, sa.Column("platform_order_no", sa.String(64), nullable=True))
    _replace_scope_checks(NEW_ONE_SCOPE, NEW_SCOPE_REF_MATCHES)
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
    # 先做完全部检查再动表：两列只要有值就拒绝回滚、不删数据
    for table, column in (
        (REVIEW_ACTIONS, "idempotency_key"),
        (COST_ENTRIES, "revoke_idempotency_key"),
        (COST_ENTRIES, "platform_order_no"),
    ):
        found = bind.execute(sa.text(f"select 1 from {table} where {column} is not null limit 1"))
        if found.first() is not None:
            raise RuntimeError(f"rollback blocked: {table}.{column} has data")
    bind.execute(
        sa.text("DELETE FROM app_permissions WHERE permission_key = ANY(:keys)"), {"keys": keys}
    )
    op.drop_index("ix_manual_settlement_review_idem", table_name=REVIEW_ACTIONS)
    op.drop_column(REVIEW_ACTIONS, "idempotency_key")
    op.drop_column(COST_ENTRIES, "revoke_idempotency_key")
    _replace_scope_checks(OLD_ONE_SCOPE, OLD_SCOPE_REF_MATCHES)
    op.drop_column(COST_ENTRIES, "platform_order_no")
