"""Finance: payout reconciliation (回款对账) — payout account map, arrival matches,
review events and follow-ups on top of 0084's Walmart bill periods.

Also registers the review1 / review2 / follow action permissions on 回款对账.
Tables start empty; real payout accounts are entered in production after launch.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261110_0085_finance_payout_recon"
down_revision: str | Sequence[str] | None = "20261108_0084_finance_walmart_bills"
branch_labels = None
depends_on = None

ACCOUNTS = "cfg_walmart_payout_accounts"
MATCHES = "manual_walmart_payout_matches"
REVIEWS = "evt_walmart_payout_reviews"
FOLLOWS = "evt_walmart_payout_follow_ups"
ACTIONS = (
    (
        "action:finance:settlement-reconciliation:review1",
        "review1",
        "回款对账初审（确认到账、配对）",
    ),
    (
        "action:finance:settlement-reconciliation:review2",
        "review2",
        "回款对账终审（通过 / 驳回、收款账户映射）",
    ),
    ("action:finance:settlement-reconciliation:follow", "follow", "回款对账打款异常跟进"),
)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        ACCOUNTS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column(
            "account_key",
            sa.String(64),
            sa.ForeignKey("dim_finance_cash_accounts.account_key"),
            nullable=False,
        ),
        sa.Column("payee", sa.Text(), nullable=False, server_default=""),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("change_reason", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        _ts("created_at"),
        sa.Column("updated_by", sa.String(255), nullable=False),
        _ts("updated_at"),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_range"
        ),
    )
    op.create_index(
        "ix_cfg_walmart_payout_accounts_store", ACCOUNTS, ["store_id", "effective_from"]
    )
    op.create_index(
        "uq_cfg_walmart_payout_accounts_store_from",
        ACCOUNTS,
        ["source_account_ref", "store_id", "effective_from"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        MATCHES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "line_uid",
            sa.String(16),
            sa.ForeignKey("std_finance_cashflow_lines.line_uid"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("report_key", sa.String(64), nullable=False),
        sa.Column("payable_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("memo_before", sa.Text()),
        sa.Column("memo_set", sa.Text()),
        sa.Column("category_set", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        _ts("created_at"),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("undone_by", sa.String(255)),
        sa.Column("undo_reason", sa.Text()),
        sa.CheckConstraint("method IN ('auto', 'manual')", name="method"),
        sa.CheckConstraint("seq >= 0", name="seq_nonnegative"),
    )
    op.create_index(
        "uq_manual_walmart_payout_matches_period",
        MATCHES,
        ["source_account_ref", "store_id", "report_key"],
        unique=True,
        postgresql_where=sa.text("undone_at IS NULL"),
    )
    op.create_index(
        "uq_manual_walmart_payout_matches_line",
        MATCHES,
        ["line_uid", "seq"],
        unique=True,
        postgresql_where=sa.text("undone_at IS NULL"),
    )
    op.create_index("ix_manual_walmart_payout_matches_match", MATCHES, ["match_id"])

    op.create_table(
        REVIEWS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("seq_no", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("report_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128)),
        _ts("created_at"),
        sa.CheckConstraint(
            "kind IN ('review1_pass', 'review2_pass', 'review2_reject', 'reset')", name="kind"
        ),
    )
    op.create_index(
        "ix_evt_walmart_payout_reviews_period",
        REVIEWS,
        ["source_account_ref", "store_id", "report_key", "created_at"],
    )

    op.create_table(
        FOLLOWS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("report_key", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("case_no", sa.String(128)),
        sa.Column("next_follow_date", sa.Date()),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128)),
        _ts("created_at"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="content_not_blank"),
    )
    op.create_index(
        "ix_evt_walmart_payout_follow_ups_period",
        FOLLOWS,
        ["source_account_ref", "store_id", "report_key", "created_at"],
    )

    bind = op.get_bind()
    for order, (key, action, name) in enumerate(ACTIONS, start=2):
        bind.execute(
            sa.text(
                """INSERT INTO app_permissions
         (permission_key,name,group_key,description,permission_type,module_key,page_key,
          action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
         VALUES (:key,:name,'finance',:name,'action','finance','finance_settlement_reconciliation',
          :action,NULL,'normal',:sort,true,now(),now())
         ON CONFLICT(permission_key) DO NOTHING"""
            ),
            {"key": key, "name": name, "action": action, "sort": 70040 + order},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (ACCOUNTS, MATCHES, REVIEWS, FOLLOWS):
        if bind.execute(sa.text(f"select 1 from {table} limit 1")).first() is not None:
            raise RuntimeError(f"{table} has data; refusing to drop it")
    keys = [key for key, _, _ in ACTIONS]
    if bind.scalar(
        sa.text("SELECT count(*) FROM app_role_permissions WHERE permission_key = ANY(:keys)"),
        {"keys": keys},
    ):
        raise RuntimeError("PAYOUT_RECON_PERMISSION_IN_USE")
    bind.execute(
        sa.text("DELETE FROM app_permissions WHERE permission_key = ANY(:keys)"), {"keys": keys}
    )
    op.drop_index("ix_evt_walmart_payout_follow_ups_period", table_name=FOLLOWS)
    op.drop_table(FOLLOWS)
    op.drop_index("ix_evt_walmart_payout_reviews_period", table_name=REVIEWS)
    op.drop_table(REVIEWS)
    op.drop_index("ix_manual_walmart_payout_matches_match", table_name=MATCHES)
    op.drop_index("uq_manual_walmart_payout_matches_line", table_name=MATCHES)
    op.drop_index("uq_manual_walmart_payout_matches_period", table_name=MATCHES)
    op.drop_table(MATCHES)
    op.drop_index("uq_cfg_walmart_payout_accounts_store_from", table_name=ACCOUNTS)
    op.drop_index("ix_cfg_walmart_payout_accounts_store", table_name=ACCOUNTS)
    op.drop_table(ACCOUNTS)
