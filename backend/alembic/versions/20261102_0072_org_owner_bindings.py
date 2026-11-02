"""Reviewed, explicit Feishu-to-Lingxing owner identity bindings.

A business owner UID is not a Feishu open_id. Binding requires an administrator;
no automatic name-based mapping or privilege escalation is performed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261102_0072_org_owner_bindings"
down_revision: str | Sequence[str] | None = "20261102_iam_skill_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_org_owner_bindings",
        sa.Column("owner_ref", sa.String(128), primary_key=True),
        sa.Column(
            "feishu_open_id",
            sa.String(128),
            sa.ForeignKey("iam_feishu_employees.open_id"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reviewed_by", sa.String(128), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_iam_org_owner_bindings_feishu",
        "iam_org_owner_bindings",
        ["feishu_open_id"],
    )
    op.create_table(
        "iam_org_owner_binding_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_ref", sa.String(128), nullable=False),
        sa.Column("previous_open_id", sa.String(128), nullable=True),
        sa.Column("new_open_id", sa.String(128), nullable=True),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_iam_org_owner_events_ref",
        "iam_org_owner_binding_events",
        ["owner_ref", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for name in ("iam_org_owner_bindings", "iam_org_owner_binding_events"):
        if connection.scalar(sa.text(f"select count(*) from {name}")):
            raise RuntimeError("Owner identity bindings must be archived before rollback")
    op.drop_index("ix_iam_org_owner_events_ref", table_name="iam_org_owner_binding_events")
    op.drop_table("iam_org_owner_binding_events")
    op.drop_index("ix_iam_org_owner_bindings_feishu", table_name="iam_org_owner_bindings")
    op.drop_table("iam_org_owner_bindings")
