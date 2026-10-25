"""Business config: encrypted connectors, notification delivery, AI usage, and audit.

Never seed credentials or send external requests. Apply only after DB authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261025_0059_business_connector_control"
down_revision: str | Sequence[str] | None = "20261025_0058_keyword_internal_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("kind IN ('feishu_webhook','openai')", name="ck_biz_connectors_kind"),
        sa.UniqueConstraint("kind", "name", name="uq_biz_connectors_kind_name"),
    )
    op.create_table(
        "biz_notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("event_key", name="uq_biz_templates_event"),
    )
    op.create_table(
        "biz_notification_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_connectors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("cooldown_seconds BETWEEN 0 AND 86400", name="ck_biz_routes_cooldown"),
        sa.CheckConstraint("daily_limit BETWEEN 1 AND 10000", name="ck_biz_routes_limit"),
        sa.UniqueConstraint("event_key", "connector_id", name="uq_biz_routes_event_connector"),
    )
    op.create_table(
        "biz_notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "route_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_notification_routes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_connectors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','sent','failed','blocked')", name="ck_biz_deliveries_status"
        ),
        sa.UniqueConstraint(
            "connector_id", "event_key", "source_event_id", name="uq_biz_deliveries_dedupe"
        ),
    )
    op.create_index(
        "ix_biz_deliveries_retry", "biz_notification_deliveries", ["status", "next_retry_at"]
    )
    op.create_index(
        "ix_biz_deliveries_daily", "biz_notification_deliveries", ["connector_id", "created_at"]
    )

    op.create_table(
        "biz_ai_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_connectors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('pending','success','failed')", name="ck_biz_ai_usage_status"),
    )
    op.create_index("ix_biz_ai_usage_month", "biz_ai_usage", ["connector_id", "created_at"])
    op.create_table(
        "biz_config_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_biz_config_audit_at", "biz_config_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_biz_config_audit_at", table_name="biz_config_audit")
    op.drop_table("biz_config_audit")
    op.drop_index("ix_biz_ai_usage_month", table_name="biz_ai_usage")
    op.drop_table("biz_ai_usage")
    op.drop_index("ix_biz_deliveries_daily", table_name="biz_notification_deliveries")
    op.drop_index("ix_biz_deliveries_retry", table_name="biz_notification_deliveries")
    op.drop_table("biz_notification_deliveries")
    op.drop_table("biz_notification_routes")
    op.drop_table("biz_notification_templates")
    op.drop_table("biz_connectors")
