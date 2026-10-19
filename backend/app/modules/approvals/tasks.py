"""Idempotent approval inbox reminder publisher.

Only identifiers are stored. Permissions and source-account scope are checked
again when opening actual approval details.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import text

from app.celery_app import celery_app
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


def publish_due_approval_reminders(*, limit: int = 200) -> int:
    if not 1 <= limit <= 200:
        raise ValueError("approval reminder batch limit invalid")
    with get_session_factory()() as session:
        # Registration of account scope is already checked at application time.
        rows = (
            session.execute(
                text("""
            select a.id::text approval_id,a.approval_type,a.applicant_id,
                   a.source_account_ref,a.version,
                   a.submitted_at + make_interval(hours=>r.due_hours) due_at
            from app_approval_requests a
            join app_approval_rules r on r.approval_type=a.approval_type
            where a.status='submitted'
            order by a.submitted_at,a.id limit :limit
        """),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
        inserted = 0
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        for item in rows:
            # WFS uses canonical archive review permission; generic
            # purchase/finance/access requests remain super-admin only.
            required = "action:warehouse:wfs-fee-alert:archive-review"
            reviewers = (
                session.execute(
                    text("""
                select distinct u.id::text reviewer
                from app_users u
                left join app_user_roles ur on ur.user_id=u.id
                left join app_role_permissions rp on rp.role_id=ur.role_id
                where u.is_active=1 and u.id::text <> :applicant
                  and (
                    u.is_super_admin=1 or (
                      :kind='wfs_case_abandon'
                      and rp.permission_key=:required
                      and (
                        exists (
                          select 1 from app_user_data_scopes uds
                          where uds.user_id=u.id and uds.scope_type='source_account'
                            and uds.scope_value in ('*',:account)
                        ) or (
                          not exists (
                            select 1 from app_user_data_scopes uds
                            where uds.user_id=u.id and uds.scope_type='source_account'
                          )
                          and exists (
                            select 1 from app_user_roles urs
                            join app_role_data_scopes ds on ds.role_id=urs.role_id
                            where urs.user_id=u.id
                              and ds.scope_type='source_account'
                              and ds.scope_value in ('*',:account)
                          )
                        )
                      )
                    )
                  )
                  and not exists (
                    select 1 from app_approval_step_decisions sd
                    where sd.approval_id=cast(:approval_id as uuid)
                      and sd.reviewer_id=u.id::text
                  )
            """),
                    {
                        "kind": item["approval_type"],
                        "applicant": item["applicant_id"],
                        "account": item["source_account_ref"],
                        "required": required,
                        "approval_id": item["approval_id"],
                    },
                )
                .scalars()
                .all()
            )
            overdue = item["due_at"] <= now
            key = ("overdue:" if overdue else "pending:") + str(item["version"])
            for reviewer in reviewers:
                result = session.execute(
                    text("""
                    insert into app_approval_notifications
                      (id,approval_id,event_key,recipient_id)
                    values (:id,cast(:approval_id as uuid),:key,:recipient)
                    on conflict do nothing
                """),
                    {
                        "id": str(uuid4()),
                        "approval_id": item["approval_id"],
                        "key": key,
                        "recipient": reviewer,
                    },
                )
                inserted += result.rowcount
        session.commit()
    return inserted


@celery_app.task(name="approvals.reminder_tick", ignore_result=True)  # type: ignore[misc]
def reminder_tick() -> None:
    count = publish_due_approval_reminders()
    logger.info("approval_reminder_tick published=%s", count)
