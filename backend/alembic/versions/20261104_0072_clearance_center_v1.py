"""Listing-level WFS clearance requests, rule versions and approval policy.

Revision ID: 20261104_0072_clearance_v1
Revises: 20261102_0071_skill_lib

No historical clearance mock tasks are migrated. Existing approval tables stay intact.
"""

from __future__ import annotations
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261104_0072_clearance_v1"
down_revision: str | Sequence[str] | None = "20261102_0071_skill_lib"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_clearance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mart_listing_management_current.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("requester_id", sa.String(128), nullable=False),
        sa.Column("target_qty", sa.Integer, nullable=False),
        sa.Column("methods", postgresql.JSONB, nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("remark", sa.Text, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column("proposed_price", sa.Numeric(18, 4)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("risk_level", sa.String(12), nullable=False),
        sa.Column("rule_version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column(
            "approval_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_approval_requests.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column("sold_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("removed_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("disposed_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
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
        sa.CheckConstraint(
            "target_qty > 0 and sold_qty >= 0 and removed_qty >= 0 and disposed_qty >= 0 and sold_qty + removed_qty + disposed_qty <= target_qty",
            name="ck_clearance_qty",
        ),
        sa.CheckConstraint("version > 0", name="ck_clearance_version"),
        sa.CheckConstraint(
            "status in ('pending','approved','rejected','withdrawn','running','paused','done')",
            name="ck_clearance_status",
        ),
    )
    op.create_index(
        "ix_clearance_listing",
        "ops_clearance_requests",
        ["source_account_ref", "store_id", "item_id"],
    )
    op.execute(
        sa.text("""create unique index uq_clearance_active_listing on ops_clearance_requests
      (source_account_ref,store_id,item_id)
      where status in ('pending','approved','running','paused')""")
    )
    op.create_table(
        "ops_clearance_rule_sets",
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "rules_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("updated_by", sa.String(128)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "ops_clearance_rule_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("rules_json", postgresql.JSONB, nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # RBAC v2 action permissions require page/action shape metadata.
    for key, label, action_key, page_key in (
        ("action:products:clearance:apply", "清货申请", "apply", "products_clearance_center"),
        ("action:products:clearance:review", "清货审批", "review", "data_center_approval_workspace"),
        ("action:products:clearance:configure", "清货规则配置", "configure", "products_clearance_center"),
        ("action:products:clearance:progress", "清货执行进度", "progress", "products_clearance_center"),
    ):
        op.execute(
            sa.text(
                """insert into app_permissions
                  (permission_key,name,group_key,description,permission_type,
                   module_key,page_key,action_key,risk_level,sort_order,is_active)
                   values (:key,:label,'products','清货中心 V1','action',
                           'products',:page,:action,'high',0,true)
                   on conflict(permission_key) do update set
                     name=excluded.name,group_key=excluded.group_key,
                     description=excluded.description,permission_type='action',
                     module_key=excluded.module_key,page_key=excluded.page_key,
                     action_key=excluded.action_key,risk_level='high',
                     is_active=true,updated_at=now()"""
            ),
            {"key": key, "label": label, "page": page_key, "action": action_key},
        )
    op.execute(
        sa.text("""insert into app_role_permissions(role_id,permission_key,created_at)
      select r.id,p.permission_key,now() from app_roles r cross join app_permissions p
      where p.permission_key like 'action:products:clearance:%'
        and (r.role_key='admin' or (r.role_key='operations' and p.permission_key in
        ('action:products:clearance:apply','action:products:clearance:progress')))
      on conflict do nothing""")
    )
    op.execute(
        sa.text("""insert into app_approval_rules(id,approval_type,title,required_steps,min_reason_length,due_hours,allows_bulk,is_active)
      values (gen_random_uuid(),'clearance_request','清货审批',1,5,48,false,true)
      on conflict(approval_type) do nothing""")
    )


def downgrade() -> None:
    # Explicit downgrade only on isolated environments; production data must be backed up first.
    op.execute(sa.text("delete from app_approval_rules where approval_type='clearance_request'"))
    op.drop_table("ops_clearance_rule_events")
    op.drop_table("ops_clearance_rule_sets")
    op.drop_index("uq_clearance_active_listing", table_name="ops_clearance_requests")
    op.drop_index("ix_clearance_listing", table_name="ops_clearance_requests")
    op.drop_table("ops_clearance_requests")
