"""Account-qualified Feishu-to-Lingxing owner identity binding.

A Lingxing owner UID can exist in more than one source account. Authorization
must bind (source_account_ref, owner_ref) independently; no name-based matching
or cross-account identity inheritance is permitted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0074_account_owner_bindings"
down_revision: str | Sequence[str] | None = "20261104_0073_feishu_org_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_org_owner_account_bindings",
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
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
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "length(btrim(source_account_ref)) > 0",
            name="ck_iam_owner_accounts_nonblank_account",
        ),
        sa.CheckConstraint(
            "length(btrim(owner_ref)) > 0",
            name="ck_iam_owner_accounts_nonblank_owner",
        ),
    )
    op.create_index(
        "ix_iam_owner_account_bindings_feishu",
        "iam_org_owner_account_bindings",
        ["feishu_open_id"],
    )
    op.create_table(
        "iam_org_owner_account_binding_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("owner_ref", sa.String(128), nullable=False),
        sa.Column("previous_open_id", sa.String(128), nullable=True),
        sa.Column("new_open_id", sa.String(128), nullable=True),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_iam_owner_account_events_identity",
        "iam_org_owner_account_binding_events",
        ["source_account_ref", "owner_ref", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for name in (
        "iam_org_owner_account_bindings",
        "iam_org_owner_account_binding_events",
    ):
        if connection.scalar(sa.text(f"select count(*) from {name}")):
            raise RuntimeError("Account-qualified owner audit data must be archived before rollback")
    op.drop_index(
        "ix_iam_owner_account_events_identity",
        table_name="iam_org_owner_account_binding_events",
    )
    op.drop_table("iam_org_owner_account_binding_events")
    op.drop_index(
        "ix_iam_owner_account_bindings_feishu",
        table_name="iam_org_owner_account_bindings",
    )
    op.drop_table("iam_org_owner_account_bindings")
