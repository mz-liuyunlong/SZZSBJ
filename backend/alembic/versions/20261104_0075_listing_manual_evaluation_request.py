"""Record scope-bound manual requests to calculate all Listings."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0075_listing_manual_evaluation_request"
down_revision: str | Sequence[str] | None = "20261104_0074_listing_lifecycle_adjustment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_listing_evaluation_manual_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_date_cn", sa.Date(), nullable=False),
        sa.Column("cutoff_date_la", sa.Date(), nullable=False),
        sa.Column("account_scope_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("biz_listing_evaluation_runs.id")
        ),
        sa.Column("error_code", sa.String(128)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_biz_listing_evaluation_manual_requests_status",
        ),
    )
    op.create_index(
        "ix_listing_evaluation_manual_status",
        "biz_listing_evaluation_manual_requests",
        ["status", "requested_at"],
    )
    op.execute(
        sa.text("""
            INSERT INTO app_permissions
              (permission_key, name, group_key, description, permission_type,
               module_key, page_key, action_key, field_key, risk_level,
               sort_order, is_active, created_at, updated_at)
            VALUES
              ('action:products:listing-management:calculate-all',
               '计算全部Listing', 'products', '请求全部Listing异步诊断，不自动发布',
               'action', 'products', 'products_listing_management',
               'calculate_all', NULL, 'high', 100, true, now(), now())
            ON CONFLICT (permission_key) DO NOTHING
        """)
    )


def downgrade() -> None:
    raise RuntimeError("LISTING_EVALUATION_REQUEST_AUDIT_REQUIRES_VERIFIED_BACKUP_RESTORE")
