"""add auth rbac tables

Revision ID: 20261010_0034_add_auth_rbac
Revises: 20261010_0033_add_wfs_low_price_surcharge
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261010_0034_add_auth_rbac"
down_revision: str | Sequence[str] | None = "20261010_0033_add_wfs_low_price_surcharge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ADMIN_ROLE_ID = "11111111-1111-4111-8111-111111111111"
OPERATIONS_ROLE_ID = "22222222-2222-4222-8222-222222222222"
FINANCE_ROLE_ID = "33333333-3333-4333-8333-333333333333"
WAREHOUSE_ROLE_ID = "44444444-4444-4444-8444-444444444444"
PURCHASE_ROLE_ID = "55555555-5555-4555-8555-555555555555"


PERMISSIONS = (
    ("products:read", "产品查看", "产品", "查看产品、Listing、产品基础资料"),
    ("sales:daily-sales:read", "销售查看", "销售", "查看每日销售和订单利润"),
    ("aftersales:refund-management:read", "售后查看", "售后", "查看退款退货数据"),
    ("warehouse:wfs-fee-alert:read", "仓库查看", "仓库", "查看库存和 WFS 异常"),
    ("pmc:purchase:read", "采购查看", "采购", "查看采购看板"),
    ("operations:plan:read", "运营计划查看", "运营", "查看运营计划"),
    ("operations:plan:write", "运营计划维护", "运营", "维护运营计划"),
    ("integrations:read", "同步查看", "数据中心", "查看同步任务和接口"),
    ("integrations:update", "同步配置", "数据中心", "维护同步配置"),
    ("integrations:execute", "同步执行", "数据中心", "执行同步任务"),
    ("business-rules:read", "规则查看", "设置", "查看业务规则"),
    ("business-rules:write", "规则维护", "设置", "维护业务规则"),
    ("business-rules:execute", "规则执行", "设置", "执行规则重算"),
    ("settings:users:read", "用户查看", "系统设置", "查看用户管理"),
    ("settings:users:write", "用户维护", "系统设置", "新增、编辑、停用、重置用户"),
    ("settings:roles:read", "角色查看", "系统设置", "查看角色和权限"),
    ("settings:roles:write", "角色维护", "系统设置", "维护角色和权限"),
)


def _execute(statement: str, params: dict[str, object] | None = None) -> None:
    op.get_bind().execute(text(statement), params or {})


def upgrade() -> None:
    _execute("create sequence if not exists app_users_id_seq")
    _execute(
        """
        select setval(
            'app_users_id_seq',
            greatest(coalesce((select max(id) from app_users), 0) + 1, 1),
            false
        )
        """
    )
    _execute("alter table app_users alter column id set default nextval('app_users_id_seq')")
    _execute("alter sequence app_users_id_seq owned by app_users.id")

    _execute("alter table app_users add column if not exists display_name varchar(128)")
    _execute("alter table app_users add column if not exists phone varchar(32)")
    _execute("alter table app_users add column if not exists email varchar(255)")
    _execute("alter table app_users add column if not exists feishu_name varchar(128)")
    _execute("alter table app_users add column if not exists feishu_open_id varchar(128)")
    _execute("alter table app_users add column if not exists feishu_user_id varchar(128)")
    _execute("alter table app_users add column if not exists feishu_union_id varchar(128)")
    _execute("alter table app_users add column if not exists feishu_employee_id varchar(128)")
    _execute("alter table app_users add column if not exists feishu_department_ids varchar(512)")
    _execute("alter table app_users add column if not exists feishu_last_synced_at timestamptz")
    _execute(
        "alter table app_users add column if not exists is_super_admin smallint not null default 0"
    )
    _execute("alter table app_users add column if not exists last_login_at timestamptz")
    _execute("alter table app_users add column if not exists password_updated_at timestamptz")
    _execute(
        "create unique index if not exists ix_app_users_feishu_open_id "
        "on app_users (feishu_open_id) where feishu_open_id is not null"
    )
    _execute(
        "create index if not exists ix_app_users_feishu_user_id "
        "on app_users (feishu_user_id) where feishu_user_id is not null"
    )
    _execute(
        "create index if not exists ix_app_users_feishu_union_id "
        "on app_users (feishu_union_id) where feishu_union_id is not null"
    )

    _execute(
        """
        create table if not exists app_roles (
            id uuid primary key,
            role_key varchar(64) not null unique,
            name varchar(64) not null,
            description varchar(255),
            is_system smallint not null default 0,
            created_at timestamptz not null,
            updated_at timestamptz not null
        )
        """
    )
    _execute("create index if not exists ix_app_roles_role_key on app_roles (role_key)")

    _execute(
        """
        create table if not exists app_permissions (
            permission_key varchar(128) primary key,
            name varchar(64) not null,
            group_key varchar(64) not null,
            description varchar(255)
        )
        """
    )
    _execute(
        "create index if not exists ix_app_permissions_group_key on app_permissions (group_key)"
    )

    _execute(
        """
        create table if not exists app_role_permissions (
            role_id uuid not null references app_roles(id) on delete cascade,
            permission_key varchar(128) not null
                references app_permissions(permission_key) on delete cascade,
            created_at timestamptz not null,
            primary key (role_id, permission_key)
        )
        """
    )

    _execute(
        """
        create table if not exists app_user_roles (
            user_id integer not null references app_users(id) on delete cascade,
            role_id uuid not null references app_roles(id) on delete cascade,
            created_at timestamptz not null,
            primary key (user_id, role_id)
        )
        """
    )
    _execute("create index if not exists ix_app_user_roles_user_id on app_user_roles (user_id)")
    _execute("create index if not exists ix_app_user_roles_role_id on app_user_roles (role_id)")

    _execute(
        """
        create table if not exists app_sessions (
            id uuid primary key,
            user_id integer not null references app_users(id) on delete cascade,
            token_hash char(64) not null unique,
            created_at timestamptz not null,
            expires_at timestamptz,
            last_seen_at timestamptz,
            revoked_at timestamptz
        )
        """
    )
    _execute("create index if not exists ix_app_sessions_user_id on app_sessions (user_id)")
    _execute("create index if not exists ix_app_sessions_expires_at on app_sessions (expires_at)")
    _execute("create index if not exists ix_app_sessions_revoked_at on app_sessions (revoked_at)")

    for permission_key, name, group_key, description in PERMISSIONS:
        _execute(
            """
            insert into app_permissions (permission_key, name, group_key, description)
            values (:permission_key, :name, :group_key, :description)
            on conflict (permission_key) do update set
                name = excluded.name,
                group_key = excluded.group_key,
                description = excluded.description
            """,
            {
                "permission_key": permission_key,
                "name": name,
                "group_key": group_key,
                "description": description,
            },
        )

    for role_id, role_key, name, description in (
        (ADMIN_ROLE_ID, "admin", "管理员", "系统管理员，拥有全部权限"),
        (OPERATIONS_ROLE_ID, "operations", "运营", "运营人员默认角色"),
        (FINANCE_ROLE_ID, "finance", "财务", "财务人员默认角色"),
        (WAREHOUSE_ROLE_ID, "warehouse", "仓库", "仓库人员默认角色"),
        (PURCHASE_ROLE_ID, "purchase", "采购", "采购人员默认角色"),
    ):
        _execute(
            """
            insert into app_roles (
                id, role_key, name, description, is_system, created_at, updated_at
            )
            values (:id, :role_key, :name, :description, 1, now(), now())
            on conflict (role_key) do update set
                name = excluded.name,
                description = excluded.description,
                updated_at = now()
            """,
            {
                "id": role_id,
                "role_key": role_key,
                "name": name,
                "description": description,
            },
        )

    _execute(
        """
        insert into app_role_permissions (role_id, permission_key, created_at)
        select cast(:role_id as uuid), permission_key, now()
        from app_permissions
        on conflict do nothing
        """,
        {"role_id": ADMIN_ROLE_ID},
    )

    _execute(
        """
        insert into app_role_permissions (role_id, permission_key, created_at)
        select cast(:role_id as uuid), permission_key, now()
        from app_permissions
        where permission_key in (
            'products:read',
            'sales:daily-sales:read',
            'aftersales:refund-management:read',
            'operations:plan:read',
            'operations:plan:write'
        )
        on conflict do nothing
        """,
        {"role_id": OPERATIONS_ROLE_ID},
    )

    _execute(
        """
        update app_users
        set is_super_admin = 1,
            display_name = coalesce(display_name, username),
            updated_at = updated_at
        where username = 'admin'
        """
    )
    _execute(
        """
        insert into app_users (user_id, role_id, created_at)
        select id, cast(:role_id as uuid), now()
        from app_users
        where username = 'admin'
        on conflict do nothing
        """,
        {"role_id": ADMIN_ROLE_ID},
    )
    _execute("update app_users set display_name = coalesce(display_name, username)")

    op.execute("""
        create table if not exists iam_password_reset_tokens (
            id uuid primary key default gen_random_uuid(),
            user_id integer not null references app_users(id) on delete cascade,
            token_hash varchar(128) not null,
            purpose varchar(32) not null,
            delivery_channel varchar(32) not null,
            delivery_target varchar(255),
            expires_at timestamptz,
            used_at timestamptz,
            created_at timestamptz not null default now(),
            request_ip varchar(64),
            user_agent text,
            is_revoked boolean not null default false
        )
    """)
    _execute("alter table iam_password_reset_tokens alter column expires_at drop not null")

    op.execute("""
        create unique index if not exists ix_iam_password_reset_tokens_token_hash
        on iam_password_reset_tokens (token_hash)
    """)
    op.execute("""
        create index if not exists ix_iam_password_reset_tokens_user_id_created
        on iam_password_reset_tokens (user_id, created_at)
    """)


def downgrade() -> None:

    op.execute("drop index if exists ix_iam_password_reset_tokens_user_id_created")
    op.execute("drop index if exists ix_iam_password_reset_tokens_token_hash")
    op.execute("drop table if exists iam_password_reset_tokens")

    _execute("drop table if exists app_sessions")
    _execute("drop table if exists app_users")
    _execute("drop table if exists app_role_permissions")
    _execute("drop table if exists app_permissions")
    _execute("drop table if exists app_roles")
    _execute("alter table app_users drop column if exists password_updated_at")
    _execute("alter table app_users drop column if exists last_login_at")
    _execute("alter table app_users drop column if exists is_super_admin")
    _execute("alter table app_users drop column if exists email")
    _execute("alter table app_users drop column if exists phone")
    _execute("alter table app_users drop column if exists display_name")
    _execute("alter table app_users alter column id drop default")
    _execute("drop sequence if exists app_users_id_seq")
