"""initial skyc v2 core tables draft

Revision ID: 0001_initial_skyc_v2
Revises: 
Create Date: 2026-09-01

This is a draft template. Review carefully before running in any environment.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_skyc_v2"
down_revision = None
branch_labels = None
depends_on = None


def uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "sys_user",
        uuid_pk(),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        *timestamps(),
    )

    op.create_table(
        "sys_role",
        uuid_pk(),
        sa.Column("role_code", sa.String(100), nullable=False, unique=True),
        sa.Column("role_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "sys_permission",
        uuid_pk(),
        sa.Column("permission_key", sa.String(200), nullable=False, unique=True),
        sa.Column("permission_name", sa.String(200), nullable=False),
        sa.Column("permission_type", sa.String(50), nullable=False),
        sa.Column("module_key", sa.String(100), nullable=True),
        sa.Column("page_key", sa.String(100), nullable=True),
        sa.Column("action_key", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_high_risk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "sys_user_role",
        uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_role.id"), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_sys_user_role"),
        *timestamps(),
    )

    op.create_table(
        "sys_role_permission",
        uuid_pk(),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_role.id"), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_permission.id"), nullable=False),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_sys_role_permission"),
        *timestamps(),
    )

    op.create_table(
        "sys_page_data_scope",
        uuid_pk(),
        sa.Column("subject_type", sa.String(20), nullable=False),  # role / user
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_key", sa.String(100), nullable=False),
        sa.Column("scope_mode", sa.String(50), nullable=False),
        sa.Column("scope_resource", sa.String(50), nullable=False),
        sa.Column("scope_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "org_unit",
        uuid_pk(),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("org_code", sa.String(100), nullable=False, unique=True),
        sa.Column("org_name", sa.String(100), nullable=False),
        sa.Column("org_type", sa.String(50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "org_user_membership",
        uuid_pk(),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_unit.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column("member_type", sa.String(50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "core_product_owner",
        uuid_pk(),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("msku", sa.String(100), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column("owner_type", sa.String(50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )

    op.create_table(
        "biz_fee_rule",
        uuid_pk(),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("store_id", sa.String(100), nullable=True),
        sa.Column("fee_type", sa.String(100), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("rule_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *timestamps(),
    )

    op.create_table(
        "sys_secret",
        uuid_pk(),
        sa.Column("secret_key", sa.String(200), nullable=False, unique=True),
        sa.Column("secret_name", sa.String(200), nullable=False),
        sa.Column("secret_type", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("masked_value", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="enabled"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "audit_action_log",
        uuid_pk(),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=True),
        sa.Column("target_id", sa.String(200), nullable=True),
        sa.Column("before_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("after_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("ip", sa.String(100), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("audit_action_log")
    op.drop_table("sys_secret")
    op.drop_table("biz_fee_rule")
    op.drop_table("core_product_owner")
    op.drop_table("org_user_membership")
    op.drop_table("org_unit")
    op.drop_table("sys_page_data_scope")
    op.drop_table("sys_role_permission")
    op.drop_table("sys_user_role")
    op.drop_table("sys_permission")
    op.drop_table("sys_role")
    op.drop_table("sys_user")
