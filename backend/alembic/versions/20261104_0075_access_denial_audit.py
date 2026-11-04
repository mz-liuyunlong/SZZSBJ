"""Auditable IAM 403 denial events without credentials or business row data."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0075_access_denial_audit"
down_revision: str | Sequence[str] | None = "20261104_0074_account_owner_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_access_denial_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("route_template", sa.String(255), nullable=False),
        sa.Column("denial_stage", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("required_permissions", postgresql.JSONB(), nullable=False),
        sa.Column("scope_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_iam_denials_request",
        "iam_access_denial_events",
        ["request_id", "created_at"],
    )
    op.create_index(
        "ix_iam_denials_time",
        "iam_access_denial_events",
        ["created_at"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("select count(*) from iam_access_denial_events")):
        raise RuntimeError("IAM denial audit requires archival before rollback")
    op.drop_index("ix_iam_denials_time", table_name="iam_access_denial_events")
    op.drop_index("ix_iam_denials_request", table_name="iam_access_denial_events")
    op.drop_table("iam_access_denial_events")
