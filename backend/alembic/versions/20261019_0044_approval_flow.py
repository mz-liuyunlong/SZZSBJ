"""Approval rules, attestations and notification outbox.

Revision ID: 20261019_0044_approval_flow
Revises: 20261017_0043_purchase_board_listing_item_source

No historical cases or approval decisions are inserted by migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261019_0044_approval_flow"
down_revision: str | Sequence[str] | None = "20261017_0043_purchase_board_listing_item_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text("""
        create table app_approval_rules (
          id uuid primary key,
          approval_type varchar(80) not null unique,
          title varchar(255) not null,
          required_steps integer not null default 1
            check (required_steps between 1 and 5),
          min_reason_length integer not null default 5
            check (min_reason_length between 5 and 1000),
          due_hours integer not null default 48
            check (due_hours between 1 and 8760),
          allows_bulk boolean not null default false,
          is_active boolean not null default true,
          version integer not null default 1 check (version>0),
          updated_by varchar(128),
          updated_at timestamptz not null default now()
        )
    """)
    )
    bind.execute(
        text("""
        create table app_approval_rule_events (
          id uuid primary key,
          approval_type varchar(80) not null,
          actor_id varchar(128) not null,
          before_policy jsonb not null,
          after_policy jsonb not null,
          created_at timestamptz not null default now()
        )
    """)
    )
    bind.execute(
        text("""
        create table app_approval_attestations (
          id uuid primary key,
          case_id uuid not null references ops_wfs_fee_anomaly_cases(id)
            on delete restrict,
          approval_id uuid not null unique references app_approval_requests(id)
            on delete restrict,
          submitted_by varchar(128) not null,
          legacy_actor_claim varchar(128),
          reason_type varchar(64) not null,
          reason text not null,
          evidence text not null,
          submitted_at timestamptz not null default now(),
          unique(case_id)
        )
    """)
    )
    bind.execute(
        text("""
        create table app_approval_step_decisions (
          id uuid primary key,
          approval_id uuid not null references app_approval_requests(id)
            on delete restrict,
          step_number integer not null check(step_number between 1 and 5),
          reviewer_id varchar(128) not null,
          decision varchar(24) not null
            check(decision in ('approved','rejected','info_required')),
          note text,
          decided_at timestamptz not null default now(),
          unique(approval_id,step_number)
        )
    """)
    )
    bind.execute(
        text("""
        create table app_approval_notifications (
          id uuid primary key,
          approval_id uuid not null references app_approval_requests(id)
            on delete restrict,
          event_key varchar(128) not null,
          recipient_id varchar(128) not null,
          status varchar(16) not null default 'unread'
            check(status in ('unread','read')),
          created_at timestamptz not null default now(),
          read_at timestamptz,
          unique(approval_id,event_key,recipient_id)
        )
    """)
    )
    bind.execute(
        text("""
        create index ix_approval_notifications_unread
        on app_approval_notifications (recipient_id,status,created_at desc)
    """)
    )
    bind.execute(
        text("""
        insert into app_approval_rules
          (id,approval_type,title,required_steps,due_hours,allows_bulk)
        values
          (gen_random_uuid(),'wfs_case_abandon','WFS 放弃跟进',1,48,false),
          (gen_random_uuid(),'purchase_exception','采购异常审批',2,48,false),
          (gen_random_uuid(),'finance_exception','财务例外审批',2,24,false),
          (gen_random_uuid(),'access_change','权限变更审批',2,24,false),
          (gen_random_uuid(),'operations_plan_ack','运营计划事项确认',1,72,true)
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "app_approval_attestations",
        "app_approval_step_decisions",
        "app_approval_notifications",
        "app_approval_rule_events",
    ):
        if bind.scalar(text(f"select count(*) from {table}")):
            raise RuntimeError("Approval audit data exists: downgrade forbidden")
    bind.execute(text("drop table app_approval_notifications"))
    bind.execute(text("drop table app_approval_step_decisions"))
    bind.execute(text("drop table app_approval_attestations"))
    bind.execute(text("drop table app_approval_rule_events"))
    bind.execute(text("drop table app_approval_rules"))
