"""Finance approvals: which company's Feishu an approval came from, plus names looked up there.

第二家公司是另一个飞书企业（Rocky 2026-11-13）：审批单进同一张表，加一列公司；
已有的都是主公司。第二家的人不在系统员工表里，同步时查到的姓名存在单子上。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261113_0089_finance_approval_second_company"
down_revision: str | Sequence[str] | None = "20261112_0088_new_product_tracking_foundation"
branch_labels = None
depends_on = None

TABLE = "std_finance_feishu_approvals"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("org", sa.String(16), nullable=False, server_default="zsbj"),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "people_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_std_finance_feishu_approvals_org", TABLE, ["org"])


def downgrade() -> None:
    # 流水上还挂着第二家公司的单（YC- 单号）就不回退：旧代码不认 YC- 单号，挂单会变成找不到的单。
    # 先在日记账里把这些单摘掉再回退（复审 P3-4）。事件表里的 YC- 单号是历史记录，保留不动。
    attached = op.get_bind().scalar(
        sa.text(
            "select count(*) from manual_finance_cash_line_state "
            "where refs::text like '%YC-%' or coalesce(parts::text, '') like '%YC-%'"
        )
    )
    if attached:
        raise RuntimeError(
            "Second-company approvals (YC-) are still attached to journal lines; "
            "detach them before downgrading 0089"
        )
    # 第二家公司的单子（单号带 YC-）回到旧结构后没有公司列，删掉，免得和主公司的单混在一起。
    op.execute(sa.text(f"delete from {TABLE} where org <> 'zsbj'"))
    op.drop_index("ix_std_finance_feishu_approvals_org", table_name=TABLE)
    op.drop_column(TABLE, "people_names")
    op.drop_column(TABLE, "org")
