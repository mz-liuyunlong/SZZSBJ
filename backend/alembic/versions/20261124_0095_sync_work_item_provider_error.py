"""0095: 同步分页记录补三列——上游 HTTP 状态、上游返回码、上游 message（脱敏截断）。

沃尔玛账单同步一旦整店失败，任务中心只剩 SYNC_WALMART_BILL_RESPONSE_FAILED 一个码，
查不到领星到底回了什么。这里把失败那一页的上游信息直接落在工作项上。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261124_0095_sync_work_item_provider_error"
down_revision = "20261120_0094_walmart_ad_catalog"
branch_labels = None
depends_on = None

TABLE = "gov_integration_sync_run_work_items"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("provider_code", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("provider_message", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "provider_message")
    op.drop_column(TABLE, "provider_code")
    op.drop_column(TABLE, "http_status")
