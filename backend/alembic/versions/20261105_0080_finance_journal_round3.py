"""Finance journal round 3: manual pairing on line state, and classify rules from rocky (11-05).

- manual_finance_cash_line_state.manual_pair: lines sharing one value are one internal transfer.
- Rules: 代发收费 -> F01; Transfer from connected account -> T03 (was T02 in the seed rule);
  WorldFirst sub-account sweep line -> X01 (auto exclude, the main-account line is kept as T03).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_0080_finance_journal_round3"
# 顺序（协调定的）：0078 改摘要/拆分 → 0079 领星汇率 → 0080 本迁移 → 0081 派安盈月结单。
down_revision: str | Sequence[str] | None = "20261105_0079_lingxing_fx_rate"
branch_labels = None
depends_on = None

TABLE = "manual_finance_cash_line_state"
RULES_TABLE = "cfg_finance_cash_classify_rules"
OLD_PATTERN = "Transfer from connected account|资金归集至专用账户"
NEW_PATTERN = "资金归集至专用账户"
NEW_RULES = (
    ("text", "代发收费", "F01", 55),
    ("text", "归集-万里汇主账号", "X01", 56),
    ("text", "归集-万里汇子账号", "T03", 57),
    ("text", "Transfer from connected account", "T03", 89),
)


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("manual_pair", sa.String(40), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"UPDATE {RULES_TABLE} SET pattern = :new "
            "WHERE source = 'seed' AND pattern = :old AND category_code = 'T02'"
        ),
        {"new": NEW_PATTERN, "old": OLD_PATTERN},
    )
    for rule_type, pattern, category_code, sort_order in NEW_RULES:
        exists = bind.scalar(
            sa.text(
                f"SELECT 1 FROM {RULES_TABLE} WHERE rule_type = :rule_type AND pattern = :pattern"
            ),
            {"rule_type": rule_type, "pattern": pattern},
        )
        if exists:
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {RULES_TABLE} "
                "(rule_type, pattern, category_code, sort_order, source) "
                "VALUES (:rule_type, :pattern, :category_code, :sort_order, 'seed')"
            ),
            {
                "rule_type": rule_type,
                "pattern": pattern,
                "category_code": category_code,
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.scalar(sa.text(f"SELECT count(*) FROM {TABLE} WHERE manual_pair IS NOT NULL"))
    if used:
        raise RuntimeError(f"{TABLE} 已有 {used} 行人工配对，拒绝降级")
    for rule_type, pattern, _, _ in NEW_RULES:
        bind.execute(
            sa.text(
                f"DELETE FROM {RULES_TABLE} "
                "WHERE source = 'seed' AND rule_type = :rule_type AND pattern = :pattern"
            ),
            {"rule_type": rule_type, "pattern": pattern},
        )
    bind.execute(
        sa.text(
            f"UPDATE {RULES_TABLE} SET pattern = :old "
            "WHERE source = 'seed' AND pattern = :new AND category_code = 'T02'"
        ),
        {"new": NEW_PATTERN, "old": OLD_PATTERN},
    )
    op.drop_column(TABLE, "manual_pair")
