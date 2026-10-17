"""Formal operation logs with isolated immutable legacy history.

Revision ID: 20261017_0043_operation_logs
Revises: 20261017_0042_rbac_backfill
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261017_0043_operation_logs"
down_revision: str | Sequence[str] | None = "20261017_0042_rbac_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_system_operation_events",
        sa.Column("legacy_id", sa.BigInteger(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128)),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("object_name", sa.String(512), nullable=False),
        sa.Column("log_content", sa.Text(), nullable=False),
        sa.Column("highlight", sa.Boolean(), nullable=False),
        sa.Column("verify_status", sa.String(24), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_ops_system_event_lookup",
        "ops_system_operation_events",
        ["source_account_ref", "event_date", "store_id", "item_id", "msku"],
    )
    op.create_table(
        "ops_manual_operation_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("legacy_id", sa.BigInteger(), unique=True),
        sa.Column("source_kind", sa.String(12), nullable=False),
        sa.Column("source_account_ref", sa.String(128)),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("msku", sa.String(128), nullable=False),
        sa.Column("log_content", sa.Text(), nullable=False),
        sa.Column("work_type", sa.String(32), nullable=False, server_default="其他"),
        sa.Column(
            "work_types_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("observe_days", sa.SmallInteger()),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("actor_ref", sa.String(128)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source_kind in ('legacy', 'manual')", name="ck_ops_manual_source_kind"),
        sa.CheckConstraint("status in ('draft', 'submitted')", name="ck_ops_manual_status"),
        sa.CheckConstraint(
            "(source_kind = 'legacy' and legacy_id is not null) or "
            "(source_kind = 'manual' and legacy_id is null "
            "and source_account_ref is not null)",
            name="ck_ops_manual_origin",
        ),
    )
    op.create_index(
        "ix_ops_manual_log_lookup",
        "ops_manual_operation_logs",
        ["source_account_ref", "log_date", "store_id", "item_id", "msku"],
    )
    op.create_index(
        "uq_ops_manual_new_identity",
        "ops_manual_operation_logs",
        ["source_account_ref", "log_date", "store_id", "item_id", "msku"],
        unique=True,
        postgresql_where=sa.text("source_kind = 'manual'"),
    )
    op.create_table(
        "ops_operation_log_links",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("entry_name", sa.String(255), nullable=False),
        sa.Column("entry_url", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("entry_type in ('keyword', 'ad')", name="ck_ops_link_entry_type"),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            "entry_type",
            name="uq_ops_link_identity",
        ),
    )
    op.execute(
        """
        insert into app_permissions (
            permission_key, name, group_key, description,
            permission_type, module_key, page_key, action_key, field_key,
            risk_level, sort_order, is_active, created_at, updated_at
        )
        values (
            'action:operations:log:edit', '编辑运营日志', 'operations',
            '编辑、批量保存和提交正式运营日志', 'action', 'operations',
            'operations_log', 'edit', null, 'normal', 20, true, now(), now()
        )
        on conflict (permission_key) do nothing
        """
    )
    op.execute(
        """
        insert into app_role_permissions (role_id, permission_key, created_at)
        select r.id, 'action:operations:log:edit', now()
        from app_roles r
        where r.role_key in ('admin', 'operations')
        on conflict do nothing
        """
    )


def downgrade() -> None:
    raise RuntimeError("Imported history: destructive downgrade requires separate authorization")
