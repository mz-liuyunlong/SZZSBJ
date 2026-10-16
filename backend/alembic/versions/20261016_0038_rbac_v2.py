"""add RBAC v2 catalog, scopes, audit, and optimistic locking

Revision ID: 20261016_0038_rbac_v2
Revises: 20261016_0037_approval_workbench
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op
from app.modules.iam.permission_catalog_v2 import (
    LEGACY_PERMISSION_MAPPINGS,
    PERMISSION_DEFINITIONS,
)

revision: str = "20261016_0038_rbac_v2"
down_revision: str | Sequence[str] | None = "20261016_0037_approval_workbench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(statement: str, params: dict[str, object] | None = None) -> None:
    op.get_bind().execute(text(statement), params or {})


def upgrade() -> None:
    op.add_column(
        "app_permissions",
        sa.Column("permission_type", sa.String(length=16), nullable=False, server_default="legacy"),
    )
    op.add_column("app_permissions", sa.Column("module_key", sa.String(length=64)))
    op.add_column("app_permissions", sa.Column("page_key", sa.String(length=128)))
    op.add_column("app_permissions", sa.Column("action_key", sa.String(length=64)))
    op.add_column("app_permissions", sa.Column("field_key", sa.String(length=64)))
    op.add_column(
        "app_permissions",
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "app_permissions",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "app_permissions",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "app_permissions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "app_permissions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "app_roles",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_check_constraint(
        "ck_app_permissions_type",
        "app_permissions",
        "permission_type in ('legacy', 'page', 'action', 'field')",
    )
    op.create_check_constraint(
        "ck_app_permissions_risk",
        "app_permissions",
        "risk_level in ('normal', 'high')",
    )
    op.create_check_constraint(
        "ck_app_permissions_shape",
        "app_permissions",
        """
        permission_type = 'legacy'
        or (
            permission_type = 'page'
            and page_key is not null
            and action_key is null
            and field_key is null
        )
        or (
            permission_type = 'action'
            and page_key is not null
            and action_key is not null
            and field_key is null
        )
        or (
            permission_type = 'field'
            and page_key is not null
            and action_key is null
            and field_key is not null
        )
        """,
    )
    op.create_index(
        "ix_app_permissions_catalog",
        "app_permissions",
        ["permission_type", "module_key", "page_key", "sort_order"],
    )

    op.create_table(
        "app_role_data_scopes",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("app_roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_value", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("role_id", "scope_type", "scope_value"),
    )
    op.create_index(
        "ix_app_role_data_scopes_lookup",
        "app_role_data_scopes",
        ["scope_type", "scope_value"],
    )

    op.create_table(
        "app_user_data_scopes",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_value", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("user_id", "scope_type", "scope_value"),
    )
    op.create_index(
        "ix_app_user_data_scopes_lookup",
        "app_user_data_scopes",
        ["scope_type", "scope_value"],
    )

    op.create_table(
        "iam_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("app_users.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_key", sa.String(length=128), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("request_id", sa.String(length=128)),
        sa.Column("request_ip", sa.String(length=64)),
        sa.Column("user_agent", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_iam_audit_events_created_at",
        "iam_audit_events",
        ["created_at"],
    )
    op.create_index(
        "ix_iam_audit_events_target",
        "iam_audit_events",
        ["target_type", "target_key", "created_at"],
    )

    for definition in PERMISSION_DEFINITIONS:
        _execute(
            """
            insert into app_permissions (
                permission_key,
                name,
                group_key,
                description,
                permission_type,
                module_key,
                page_key,
                action_key,
                field_key,
                risk_level,
                sort_order,
                is_active,
                created_at,
                updated_at
            )
            values (
                :permission_key,
                :name,
                :group_key,
                :description,
                :permission_type,
                :module_key,
                :page_key,
                :action_key,
                :field_key,
                :risk_level,
                :sort_order,
                true,
                now(),
                now()
            )
            on conflict (permission_key) do update set
                name = excluded.name,
                group_key = excluded.group_key,
                description = excluded.description,
                permission_type = excluded.permission_type,
                module_key = excluded.module_key,
                page_key = excluded.page_key,
                action_key = excluded.action_key,
                field_key = excluded.field_key,
                risk_level = excluded.risk_level,
                sort_order = excluded.sort_order,
                is_active = true,
                updated_at = now()
            """,
            {
                "permission_key": definition.permission_key,
                "name": definition.name,
                "group_key": definition.module_key,
                "description": definition.description,
                "permission_type": definition.permission_type,
                "module_key": definition.module_key,
                "page_key": definition.page_key,
                "action_key": definition.action_key,
                "field_key": definition.field_key,
                "risk_level": definition.risk_level,
                "sort_order": definition.sort_order,
            },
        )

    for legacy_key, replacement_keys in LEGACY_PERMISSION_MAPPINGS.items():
        for replacement_key in replacement_keys:
            _execute(
                """
                insert into app_role_permissions (role_id, permission_key, created_at)
                select role_id, :replacement_key, now()
                from app_role_permissions
                where permission_key = :legacy_key
                on conflict do nothing
                """,
                {
                    "legacy_key": legacy_key,
                    "replacement_key": replacement_key,
                },
            )

    _execute(
        """
        insert into app_role_data_scopes (role_id, scope_type, scope_value, created_at)
        select id, 'source_account', '*', now()
        from app_roles
        where role_key = 'admin'
        on conflict do nothing
        """
    )


def downgrade() -> None:
    _execute(
        """
        delete from app_permissions
        where permission_type in ('page', 'action', 'field')
        """
    )
    op.drop_index("ix_iam_audit_events_target", table_name="iam_audit_events")
    op.drop_index("ix_iam_audit_events_created_at", table_name="iam_audit_events")
    op.drop_table("iam_audit_events")
    op.drop_index("ix_app_user_data_scopes_lookup", table_name="app_user_data_scopes")
    op.drop_table("app_user_data_scopes")
    op.drop_index("ix_app_role_data_scopes_lookup", table_name="app_role_data_scopes")
    op.drop_table("app_role_data_scopes")
    op.drop_index("ix_app_permissions_catalog", table_name="app_permissions")
    op.drop_constraint("ck_app_permissions_shape", "app_permissions", type_="check")
    op.drop_constraint("ck_app_permissions_risk", "app_permissions", type_="check")
    op.drop_constraint("ck_app_permissions_type", "app_permissions", type_="check")
    op.drop_column("app_roles", "version")
    op.drop_column("app_permissions", "updated_at")
    op.drop_column("app_permissions", "created_at")
    op.drop_column("app_permissions", "is_active")
    op.drop_column("app_permissions", "sort_order")
    op.drop_column("app_permissions", "risk_level")
    op.drop_column("app_permissions", "field_key")
    op.drop_column("app_permissions", "action_key")
    op.drop_column("app_permissions", "page_key")
    op.drop_column("app_permissions", "module_key")
    op.drop_column("app_permissions", "permission_type")
