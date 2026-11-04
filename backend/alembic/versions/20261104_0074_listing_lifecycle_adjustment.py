"""Add audited two-person Listing lifecycle adjustments."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0074_listing_lifecycle_adjustment"
down_revision: str | Sequence[str] | None = "20261104_0073_listing_grade_default_rule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "biz_listing_evaluation_runs",
        sa.Column("published_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "biz_listing_evaluation_snapshots", sa.Column("published_at", sa.DateTime(timezone=True))
    )
    op.add_column("biz_listing_evaluation_snapshots", sa.Column("published_by", sa.String(128)))
    op.add_column(
        "biz_listing_evaluation_snapshots", sa.Column("lifecycle_evidence_reason", sa.Text())
    )
    op.add_column(
        "biz_listing_evaluation_snapshots",
        sa.Column("publication_error_code", sa.String(128)),
    )
    op.add_column(
        "biz_listing_evaluation_snapshots", sa.Column("reverted_at", sa.DateTime(timezone=True))
    )
    op.add_column("biz_listing_evaluation_snapshots", sa.Column("reverted_by", sa.String(128)))
    op.add_column("biz_listing_evaluation_snapshots", sa.Column("revert_reason", sa.Text()))
    op.create_table(
        "biz_listing_lifecycle_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("expected_stage", sa.String(64)),
        sa.Column("requested_stage", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_biz_listing_lifecycle_adjustments_status",
        ),
    )
    op.create_index(
        "ix_listing_lifecycle_adjustment_scope",
        "biz_listing_lifecycle_adjustments",
        ["source_account_ref", "listing_id"],
    )
    op.execute(
        sa.text("""
            INSERT INTO app_permissions
              (permission_key, name, group_key, description, permission_type,
               module_key, page_key, action_key, field_key, risk_level,
               sort_order, is_active, created_at, updated_at)
            VALUES
              ('action:products:listing-management:request-lifecycle',
               '申请调整Listing生命周期', 'products', '提交人工生命周期调整申请',
               'action', 'products', 'products_listing_management',
               'request_lifecycle', NULL, 'high', 80, true, now(), now()),
              ('action:products:listing-management:approve-lifecycle',
               '审批Listing生命周期调整', 'products', '由另一授权人审批人工生命周期调整',
               'action', 'products', 'products_listing_management',
               'approve_lifecycle', NULL, 'high', 90, true, now(), now()),
              ('action:products:listing-management:revert-evaluation',
               '撤回Listing评级发布', 'products', '撤回最新正式发布并保留原审计',
               'action', 'products', 'products_listing_management',
               'revert_evaluation', NULL, 'high', 110, true, now(), now())
            ON CONFLICT (permission_key) DO NOTHING
        """)
    )


def downgrade() -> None:
    raise RuntimeError("LISTING_LIFECYCLE_AUDIT_REQUIRES_VERIFIED_BACKUP_RESTORE")
