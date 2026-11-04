"""Store Feishu organization snapshots without changing accounts or permissions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261031_0070_feishu_org_snapshot"
down_revision: str | Sequence[str] | None = "20261031_0069_iam_permission_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_feishu_org_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("department_count", sa.Integer(), nullable=False),
        sa.Column("employee_count", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "iam_feishu_departments",
        sa.Column("department_id", sa.String(128), primary_key=True),
        sa.Column("parent_department_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("leader_user_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_iam_feishu_departments_parent",
        "iam_feishu_departments",
        ["parent_department_id"],
    )
    op.create_table(
        "iam_feishu_employees",
        sa.Column("open_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("department_ids", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("is_frozen", sa.Boolean()),
        sa.Column("is_resigned", sa.Boolean()),
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_iam_feishu_employees_last_seen",
        "iam_feishu_employees",
        ["last_seen_run_id"],
    )


def downgrade() -> None:
    """Never drop an occupied organization snapshot on rollback."""
    connection = op.get_bind()
    for table in (
        "iam_feishu_org_sync_runs",
        "iam_feishu_departments",
        "iam_feishu_employees",
    ):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Organization snapshots exist; explicit archival required")
    op.drop_index("ix_iam_feishu_employees_last_seen", table_name="iam_feishu_employees")
    op.drop_table("iam_feishu_employees")
    op.drop_index("ix_iam_feishu_departments_parent", table_name="iam_feishu_departments")
    op.drop_table("iam_feishu_departments")
    op.drop_table("iam_feishu_org_sync_runs")
