"""Finance journal: Feishu approval instances (expense, payment, petty cash)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261105_0077_finance_approvals"
down_revision: str | Sequence[str] | None = "20261105_0076_listing_product_tags"
branch_labels = None
depends_on = None

TABLE = "std_finance_feishu_approvals"
CONSTRAINT = "ck_gov_integration_interfaces_method_post"


def _text_column(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _json_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("instance_code", sa.String(length=64), primary_key=True),
        sa.Column("serial_number", sa.String(length=32), nullable=False),
        sa.Column("approval_code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("applicant_user_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("department_id", sa.String(length=64), nullable=False, server_default=""),
        _text_column("reason"),
        sa.Column("amount", sa.Numeric(18, 4)),
        sa.Column("currency_code", sa.String(length=8), nullable=False, server_default="CNY"),
        _text_column("pay_method"),
        _text_column("invoice"),
        _text_column("payee"),
        _text_column("payee_bank"),
        sa.Column("payee_account_last4", sa.String(length=8), nullable=False, server_default=""),
        _text_column("fee_category"),
        _text_column("related_serial"),
        _json_column("items"),
        _json_column("attachments"),
        _json_column("records"),
        _json_column("comments"),
        sa.Column("last_run_id", sa.Uuid()),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("uq_std_finance_feishu_approvals_serial", TABLE, ["serial_number"], unique=True)
    op.create_index("ix_std_finance_feishu_approvals_started", TABLE, ["started_at"])
    # 飞书审批列表是 GET：任务中心接口目录放开这一种方法，其他写法不变。
    op.drop_constraint(op.f(CONSTRAINT), "gov_integration_interfaces", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "gov_integration_interfaces", "method IN ('POST', 'GET')"
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"select 1 from {TABLE} limit 1")).first() is not None:
        raise RuntimeError(f"{TABLE} has data; refusing to drop it")
    bind = op.get_bind()
    has_get = sa.text("select 1 from gov_integration_interfaces where method <> 'POST' limit 1")
    if bind.execute(has_get).first() is not None:
        raise RuntimeError("gov_integration_interfaces has non-POST rows; refusing to downgrade")
    op.drop_constraint(op.f(CONSTRAINT), "gov_integration_interfaces", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "gov_integration_interfaces", "method = 'POST'")
    op.drop_table(TABLE)
