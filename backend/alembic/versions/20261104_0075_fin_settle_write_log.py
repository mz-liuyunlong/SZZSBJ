"""Finance settlement profit V2 write log (PRP §5 / §7, PR-4).

Creates ``manual_settlement_write_log`` (idempotent replay of Idempotency-Key for 24 h and
append-only audit of every settlement profit write) and registers the 结算利润 page,
action and field permissions in ``app_permissions`` (PRP §5).  Downgrade refuses while the
log has records or a role still grants one of these permissions; it deactivates the
permission rows instead of deleting them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

PAGE_KEY = "finance_settlement_profit"
PERMISSIONS = (
    # (permission_key, name, type, action_key, field_key, risk, sort_order)
    ("page:finance:settlement-profit:view", "结算利润", "page", None, None, "normal", 70080),
    (
        "action:finance:settlement-profit:adjust",
        "结算利润人工调整",
        "action",
        "adjust",
        None,
        "normal",
        70081,
    ),
    (
        "action:finance:settlement-profit:review-first",
        "结算利润初审",
        "action",
        "review-first",
        None,
        "normal",
        70082,
    ),
    (
        "action:finance:settlement-profit:review-final",
        "结算利润终审",
        "action",
        "review-final",
        None,
        "high",
        70083,
    ),
    (
        "action:finance:settlement-profit:close-month",
        "结算利润结账 / 反结账",
        "action",
        "close-month",
        None,
        "high",
        70084,
    ),
    (
        "action:finance:settlement-profit:config",
        "维护纯利设置",
        "action",
        "config",
        None,
        "high",
        70085,
    ),
    ("field:finance:settlement-profit:cost", "结算利润货本", "field", None, "cost", "high", 70086),
    (
        "field:finance:settlement-profit:net-profit",
        "结算利润纯利",
        "field",
        None,
        "net-profit",
        "high",
        70087,
    ),
    (
        "field:finance:settlement-profit:company-cost",
        "公司级费用",
        "field",
        None,
        "company-cost",
        "high",
        70088,
    ),
)

revision: str = "20261104_0075_fin_settle_write_log"
down_revision: str | Sequence[str] | None = "20261104_0074_fin_settle_calc"
branch_labels = None
depends_on = None

TABLE = "manual_settlement_write_log"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.CheckConstraint("idempotency_key <> ''", name="write_log_idem_not_blank"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_settlement_write_log")),
        sa.UniqueConstraint(
            "actor_id", "endpoint", "idempotency_key", name="uq_manual_settlement_write_log_idem"
        ),
    )
    op.create_index("ix_manual_settlement_write_log_acted_at", TABLE, ["acted_at"], unique=False)
    bind = op.get_bind()
    for key, name, kind, action, field, risk, order in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO app_permissions (permission_key, name, group_key, description, "
                "permission_type, module_key, page_key, action_key, field_key, risk_level, "
                "sort_order, is_active, created_at, updated_at) VALUES (:key, :name, "
                "'finance', :name, :kind, 'finance', :page, :action, :field, :risk, :order, "
                "true, now(), now()) ON CONFLICT (permission_key) DO UPDATE SET is_active = true"
            ),
            {
                "key": key,
                "name": name,
                "kind": kind,
                "page": PAGE_KEY,
                "action": action,
                "field": field,
                "risk": risk,
                "order": order,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {TABLE})")).scalar_one():
        raise RuntimeError("0075 rollback blocked: settlement profit write log has records")
    keys = [p[0] for p in PERMISSIONS]
    in_use = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM app_role_permissions WHERE permission_key = ANY(:k))"
        ),
        {"k": keys},
    ).scalar_one()
    if in_use:
        raise RuntimeError("0075 rollback blocked: a role still grants a settlement profit key")
    conn.execute(
        sa.text("UPDATE app_permissions SET is_active = false WHERE permission_key = ANY(:k)"),
        {"k": keys},
    )
    op.drop_index("ix_manual_settlement_write_log_acted_at", table_name=TABLE)
    op.drop_table(TABLE)
