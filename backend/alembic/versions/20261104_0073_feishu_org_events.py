"""Persist authenticated Feishu organization-event state for replay and audit.

The event inbox never stores callback ciphertext, raw data, tokens or secrets.
Only committed callbacks are eligible for worker reconciliation.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261104_0073_feishu_org_events"
down_revision: str | Sequence[str] | None = "20261102_0072_org_owner_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_feishu_org_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("open_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_run_id", sa.String(64), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry', 'needs_review', 'applied')",
            name="ck_iam_feishu_org_events_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_iam_feishu_org_events_attempts"),
    )
    op.create_index(
        "ix_iam_feishu_org_events_ready",
        "iam_feishu_org_events",
        ["status", "next_attempt_at", "received_at"],
    )
    op.create_index(
        "ix_iam_feishu_org_events_open",
        "iam_feishu_org_events",
        ["open_id", "received_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM iam_feishu_org_events")):
        raise RuntimeError("Feishu event audit must be archived before rollback")
    op.drop_index("ix_iam_feishu_org_events_open", table_name="iam_feishu_org_events")
    op.drop_index("ix_iam_feishu_org_events_ready", table_name="iam_feishu_org_events")
    op.drop_table("iam_feishu_org_events")
