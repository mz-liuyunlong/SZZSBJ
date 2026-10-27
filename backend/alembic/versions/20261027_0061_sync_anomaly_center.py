"""Persist business validation anomalies independently from sync runs.

Application of this migration to production requires separate authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "20261027_0061_sync_anomaly_center"
down_revision: str | Sequence[str] | None = "20261026_0060_merge_listing_business_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gov_integration_sync_anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("interface_key", sa.String(128), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=False),
        sa.Column("subject_key", sa.String(64), nullable=False),
        sa.Column("store_id", sa.String(128)),
        sa.Column("item_id", sa.String(128)),
        sa.Column("msku", sa.Text()),
        sa.Column("local_sku", sa.Text()),
        sa.Column("platform_order_no", sa.Text()),
        sa.Column("campaign_name", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("owner_note", sa.Text()),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_account_ref", "interface_key", "business_date", "error_code", "subject_key", name="uq_gov_sync_anomaly_identity"),
        sa.CheckConstraint("status IN ('pending','investigating','fix_pending','review_pending','resolved','dismissed')", name="ck_gov_sync_anomaly_status"),
    )
    op.create_index("ix_gov_sync_anomaly_scope_status", "gov_integration_sync_anomalies", ["source_account_ref", "status", "last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_gov_sync_anomaly_scope_status", table_name="gov_integration_sync_anomalies")
    op.drop_table("gov_integration_sync_anomalies")
