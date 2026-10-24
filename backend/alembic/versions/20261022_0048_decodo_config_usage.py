"""Encrypted Decodo connector settings and outbound request usage.

Migration intentionally does not fetch data or seed secrets.
Run only after explicit database migration authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "20261022_0048_decodo_config_usage"
down_revision: str | Sequence[str] | None = "20261020_0047_walmart_order_identity_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decodo_connector_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("authorization_ciphertext", sa.Text(), nullable=True),
        sa.Column("us_zip", sa.String(5), nullable=False, server_default="10001"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.String(128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_decodo_settings_singleton"),
        sa.CheckConstraint("us_zip ~ '^[0-9]{5}$'", name="ck_decodo_settings_zip"),
    )
    op.create_table(
        "decodo_request_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("identifier", sa.String(128), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column("request_date_us", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "target IN ('amazon_product','walmart_product')",
            name="ck_decodo_logs_target",
        ),
        sa.CheckConstraint(
            "status IN ('pending','success','failed')",
            name="ck_decodo_logs_status",
        ),
    )
    op.create_index(
        "ix_decodo_request_logs_us_day_target",
        "decodo_request_logs",
        ["request_date_us", "target"],
    )
    op.create_table(
        "decodo_product_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=False),
        sa.Column("identifier", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_decodo_snapshots_lookup",
        "decodo_product_snapshots",
        ["sku_id", "target", "identifier", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_decodo_snapshots_lookup", table_name="decodo_product_snapshots")
    op.drop_table("decodo_product_snapshots")
    op.drop_index("ix_decodo_request_logs_us_day_target", table_name="decodo_request_logs")
    op.drop_table("decodo_request_logs")
    op.drop_table("decodo_connector_settings")
