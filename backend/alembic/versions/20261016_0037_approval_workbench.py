"""Unified approval requests and append-only approval events.

Revision ID: 20261016_0037_approval_workbench
Revises: 20261015_0036_wfs_cases

No existing WFS records are changed or backfilled by this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261016_0037_approval_workbench"
down_revision: str | Sequence[str] | None = "20261015_0036_wfs_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        text("""
        create table app_approval_requests (
            id uuid primary key,
            approval_type varchar(80) not null,
            business_ref varchar(128) not null,
            source_account_ref varchar(128) not null,
            applicant_id varchar(128) not null,
            title varchar(255) not null,
            reason text not null,
            evidence text,
            status varchar(24) not null default 'submitted',
            risk_level varchar(12) not null,
            snapshot jsonb not null,
            snapshot_hash varchar(64) not null,
            version integer not null default 1,
            reviewed_by varchar(128),
            review_note text,
            submitted_at timestamptz not null default now(),
            reviewed_at timestamptz,
            updated_at timestamptz not null default now(),
            constraint ck_approval_status check (
              status in ('submitted','info_required','approved','rejected','withdrawn')
            ),
            constraint ck_approval_risk check (risk_level in ('low','medium','high')),
            constraint ck_approval_version check (version > 0)
        )
    """)
    )
    connection.execute(
        text("""
        create unique index uq_approval_active_business
          on app_approval_requests (approval_type, business_ref)
          where status in ('submitted','info_required')
    """)
    )
    connection.execute(
        text("""
        create index ix_approval_scope_status
          on app_approval_requests (source_account_ref, status, submitted_at desc)
    """)
    )
    connection.execute(
        text("""
        create index ix_approval_applicant
          on app_approval_requests (applicant_id, submitted_at desc)
    """)
    )
    connection.execute(
        text("""
        create table app_approval_events (
            id uuid primary key,
            approval_id uuid not null references app_approval_requests(id) on delete restrict,
            event_type varchar(32) not null,
            actor_id varchar(128) not null,
            note text,
            detail jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now()
        )
    """)
    )
    connection.execute(
        text("""
        create index ix_approval_events_request_time
          on app_approval_events (approval_id, created_at, id)
    """)
    )
    for key, label, description in (
        ("approvals:workbench:read", "审批工作台查看", "查看授权范围内的审批单"),
        (
            "approvals:workbench:review",
            "审批工作台审核",
            "审批工作台审核入口；业务审核仍需单独授权",
        ),
    ):
        connection.execute(
            text("""
            insert into app_permissions (permission_key, name, group_key, description)
            values (:key, :label, '数据中心', :description)
            on conflict (permission_key) do nothing
        """),
            {"key": key, "label": label, "description": description},
        )
    connection.execute(
        text("""
        insert into app_role_permissions (role_id, permission_key, created_at)
        select r.id, p.permission_key, now()
          from app_roles r cross join app_permissions p
         where (r.role_key = 'admin'
                and p.permission_key in (
                  'approvals:workbench:read', 'approvals:workbench:review'
                ))
            or (r.role_key in ('operations','warehouse')
                and p.permission_key = 'approvals:workbench:read')
        on conflict do nothing
    """)
    )


def downgrade() -> None:
    # Approval decisions and audit events must not be silently erased.
    connection = op.get_bind()
    count = connection.scalar(text("select count(*) from app_approval_requests"))
    if count:
        raise RuntimeError("Downgrade blocked: approval history exists")
    connection.execute(text("drop table app_approval_events"))
    connection.execute(text("drop table app_approval_requests"))
