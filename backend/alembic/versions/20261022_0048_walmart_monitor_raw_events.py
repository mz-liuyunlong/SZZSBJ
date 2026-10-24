"""Add isolated Walmart monitor RAW event storage.

Revision ID: 20261022_0048_walmart_monitor_raw_events
Revises: 20261020_0047_walmart_order_identity_guard
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261022_0048_walmart_monitor_raw_events"
down_revision: str | Sequence[str] | None = "20261020_0047_walmart_order_identity_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_walmart_monitor_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("producer_instance_id", sa.String(128), nullable=False),
        sa.Column("producer_check_id", sa.String(128), nullable=False),
        sa.Column("producer_run_id", sa.String(128), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_provider", sa.String(64), nullable=False),
        sa.Column("final_outcome", sa.String(64), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "schema_version = 'walmart-monitor.raw.v1'",
            name="ck_raw_walmart_monitor_events_schema_version_v1",
        ),
        sa.CheckConstraint(
            "target_count BETWEEN 1 AND 100",
            name="ck_raw_walmart_monitor_events_target_count",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 1 AND 20",
            name="ck_raw_walmart_monitor_events_attempt_count",
        ),
        sa.CheckConstraint(
            "raw_hash ~ '^[0-9a-f]{64}$'",
            name="ck_raw_walmart_monitor_events_raw_hash_sha256",
        ),
        sa.CheckConstraint(
            "payload_bytes > 0",
            name="ck_raw_walmart_monitor_events_payload_bytes_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_raw_walmart_monitor_events_event_id"),
    )
    op.create_index(
        "ix_raw_walmart_monitor_events_captured_at",
        "raw_walmart_monitor_events",
        ["captured_at"],
    )
    op.create_index(
        "ix_raw_walmart_monitor_events_raw_hash",
        "raw_walmart_monitor_events",
        ["raw_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_raw_walmart_monitor_events_raw_hash",
        table_name="raw_walmart_monitor_events",
    )
    op.drop_index(
        "ix_raw_walmart_monitor_events_captured_at",
        table_name="raw_walmart_monitor_events",
    )
    op.drop_table("raw_walmart_monitor_events")
