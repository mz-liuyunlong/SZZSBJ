"""Finance journal: Payoneer month-end statement rows (actual received amount per withdrawal).

Runs after journal edit (0078), Lingxing FX (0079) and journal round 3 (0080).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_0081_finance_payoneer_statement"
# 排在流水编辑 0078 → 领星汇率 0079 → 批量第三轮 0080 之后（总管 11-05 定的顺序）。
down_revision: str | Sequence[str] | None = "20261105_0080_finance_journal_round3"
branch_labels = None
depends_on = None

TABLE = "std_finance_payoneer_statement_rows"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "raw_file_id",
            sa.Uuid(),
            sa.ForeignKey("raw_finance_cashflow_files.file_id"),
            nullable=False,
        ),
        sa.Column(
            "import_id",
            sa.Uuid(),
            sa.ForeignKey("landing_finance_cashflow_imports.import_id"),
            nullable=False,
        ),
        sa.Column(
            "account_key",
            sa.String(64),
            sa.ForeignKey("dim_finance_cash_accounts.account_key"),
            nullable=False,
        ),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("txn_id", sa.String(32), nullable=False, server_default=""),
        sa.Column("txn_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("transfer_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("transfer_currency", sa.String(8), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "raw_file_id", "row_no", name="uq_std_finance_payoneer_statement_rows_raw_file_id"
        ),
    )
    op.create_index(
        "ix_std_finance_payoneer_statement_rows_account_txn", TABLE, ["account_key", "txn_id"]
    )


def downgrade() -> None:
    used = op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {TABLE}"))
    if used:
        raise RuntimeError(f"{TABLE} 已有 {used} 行派安盈月结明细，拒绝降级")
    op.drop_index("ix_std_finance_payoneer_statement_rows_account_txn", table_name=TABLE)
    op.drop_table(TABLE)
