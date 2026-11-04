"""Feature-flagged China-time scheduler for Listing diagnostic snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_engine
from app.modules.business_connectors.router import NotifyRequest, queue_notification
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.evaluation import rating_cutoff_la
from app.modules.listing_rule_config.models import (
    ListingEvaluationManualRequest,
    ListingEvaluationRun,
    ListingGradeFollowUpTask,
    ListingGradeRuleVersion,
)
from app.modules.listing_rule_config.publish import ListingEvaluationPublisher
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CHINA_TZ = ZoneInfo("Asia/Shanghai")


def account_scope_hash(accounts: set[str] | frozenset[str]) -> str:
    """Bind a queued global diagnostic to the exact authorized account universe."""
    return sha256("\0".join(sorted(accounts)).encode("utf-8")).hexdigest()


@celery_app.task(name="listing_evaluation.followup_tick", ignore_result=True)
def followup_tick() -> None:
    """Queue generic, deduplicated reminders; outbound delivery remains separately gated."""
    settings = get_settings()
    if not (
        settings.listing_evaluation_followup_notifications_enabled
        and settings.listing_evaluation_publish_enabled
    ):
        return
    now = datetime.now(CHINA_TZ)
    with Session(get_engine()) as session:
        rule = session.scalar(
            select(ListingGradeRuleVersion)
            .where(ListingGradeRuleVersion.effective_from <= now.astimezone(UTC))
            .order_by(ListingGradeRuleVersion.version.desc())
            .limit(1)
        )
        if rule is None:
            return
        follow_up = ListingGradeRuleConfig.model_validate(rule.config_json).follow_up
        active_count = (
            session.scalar(
                select(func.count())
                .select_from(ListingGradeFollowUpTask)
                .where(
                    ListingGradeFollowUpTask.status.in_(("pending", "in_progress")),
                    ListingGradeFollowUpTask.due_date_cn <= now.date(),
                )
            )
            or 0
        )
    if not active_count:
        return
    current_time = now.strftime("%H:%M")
    for configured_time, enabled, event_key, message in (
        (
            follow_up.reminder_time,
            bool(follow_up.reminder_time),
            "listing_grade_followup_reminder",
            "Listing C/D 每日跟进尚有待处理任务，请在 Listing 管理中查看。",
        ),
        (
            follow_up.deadline_time,
            follow_up.overdue_notice,
            "listing_grade_followup_overdue",
            "Listing C/D 每日跟进已有逾期任务，请在 Listing 管理中查看。",
        ),
    ):
        if enabled and configured_time is not None and current_time >= configured_time:
            queue_notification(
                NotifyRequest(
                    event_key=event_key,
                    source_event_id=f"listing-followup-{event_key}-{now.date().isoformat()}",
                    text=message,
                ),
                actor="system:listing-evaluation",
            )


@celery_app.task(name="listing_evaluation.manual_diagnostic", ignore_result=True)
def manual_diagnostic(request_id: str) -> None:
    """Run one audited all-Listing diagnostic; manual requests never publish."""
    with (
        get_engine().connect() as connection,
        Session(bind=connection, autoflush=False, expire_on_commit=False) as session,
    ):
        locked = session.scalar(text("SELECT pg_try_advisory_lock(2406251026)"))
        try:
            request = session.get(ListingEvaluationManualRequest, UUID(request_id))
            if request is None or request.status != "queued":
                return
            if not get_settings().listing_evaluation_manual_enabled:
                request.status = "failed"
                request.error_code = "LISTING_EVALUATION_MANUAL_DISABLED"
                request.finished_at = datetime.now(UTC)
                session.commit()
                return
            if not locked:
                request.status = "failed"
                request.error_code = "LISTING_EVALUATION_BUSY"
                request.finished_at = datetime.now(UTC)
                session.commit()
                return
            accounts = set(
                session.scalars(
                    select(ListingManagementCurrentMart.source_account_ref).distinct()
                ).all()
            )
            if (
                not accounts
                or account_scope_hash(accounts) != request.account_scope_hash
                or datetime.now(UTC) - request.requested_at > timedelta(hours=1)
            ):
                request.status = "failed"
                request.error_code = "LISTING_EVALUATION_SCOPE_OR_TIME_CHANGED"
                request.finished_at = datetime.now(UTC)
                session.commit()
                return
            request.status = "running"
            session.commit()
            try:
                run_id = ListingEvaluationBatchService(session).run_daily_diagnostic(
                    schedule_date_cn=request.schedule_date_cn,
                    cutoff_date_la=request.cutoff_date_la,
                    batch_size=50,
                    replay_succeeded=True,
                )
            except Exception:
                session.rollback()
                failed = session.get(ListingEvaluationManualRequest, request.id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error_code = "LISTING_EVALUATION_MANUAL_FAILED"
                    failed.finished_at = datetime.now(UTC)
                    session.commit()
                return
            request = session.get(ListingEvaluationManualRequest, request.id)
            if request is not None:
                request.run_id = run_id
                run = session.get(ListingEvaluationRun, run_id)
                request.status = (
                    "succeeded" if run is not None and run.status == "succeeded" else "failed"
                )
                if request.status == "failed":
                    request.error_code = "LISTING_EVALUATION_BATCH_INCOMPLETE"
                request.finished_at = datetime.now(UTC)
                session.commit()
        finally:
            if locked:
                session.execute(text("SELECT pg_advisory_unlock(2406251026)"))


def rule_is_due(row: ListingGradeRuleVersion | None, now: datetime) -> bool:
    config = (
        ListingGradeRuleConfig.model_validate(row.config_json)
        if row is not None
        else ListingGradeRuleConfig()
    )
    if row is not None and now < row.effective_from:
        return False
    return now.astimezone(CHINA_TZ).strftime("%H:%M") >= config.execution_time


@celery_app.task(name="listing_evaluation.scheduler_tick", ignore_result=True)
def scheduler_tick() -> None:
    """Run only when explicitly enabled and at the saved China-time minute."""
    if not get_settings().listing_evaluation_scheduler_enabled:
        return
    now = datetime.now(UTC)
    local = now.astimezone(CHINA_TZ)
    # Bind the ORM session to one explicit physical connection. Session-level
    # advisory locks otherwise risk being unlocked on a different pooled
    # connection after the batch commits between pages.
    with (
        get_engine().connect() as connection,
        Session(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
        ) as session,
    ):
        locked = session.scalar(text("SELECT pg_try_advisory_lock(2406251026)"))
        if not locked:
            return
        try:
            row = session.scalar(
                select(ListingGradeRuleVersion)
                .where(ListingGradeRuleVersion.effective_from <= now)
                .order_by(ListingGradeRuleVersion.version.desc())
                .limit(1)
            )
            # A newly saved schedule supersedes the prior schedule immediately,
            # while its explicit boundary prevents an earlier catch-up run.
            if not rule_is_due(row, now):
                return
            existing_run = session.scalar(
                select(ListingEvaluationRun)
                .where(ListingEvaluationRun.schedule_date_cn == local.date())
                .order_by(ListingEvaluationRun.attempt_count.desc())
                .limit(1)
            )
            if existing_run is not None and existing_run.status == "succeeded":
                # Manual calculations are diagnostics only, including on later beat ticks.
                manual_run = session.scalar(
                    select(ListingEvaluationManualRequest.id)
                    .where(ListingEvaluationManualRequest.run_id == existing_run.id)
                    .limit(1)
                )
                if manual_run is not None:
                    return
                if get_settings().listing_evaluation_publish_enabled:
                    ListingEvaluationPublisher(session).publish_run(run_id=existing_run.id)
                    ListingEvaluationBatchService(session).create_followups_for_published_run(
                        run_id=existing_run.id
                    )
                return
            if existing_run is not None and existing_run.status in {"queued", "running"}:
                # The advisory lock is held for the entire run. Reaching this
                # point with an old in-progress row means its process exited.
                # Keep its snapshots and record an explicit failed attempt.
                if (
                    existing_run.last_dispatch_at is None
                    or existing_run.last_dispatch_at > now - timedelta(minutes=15)
                ):
                    return
                existing_run.status = "failed"
                existing_run.error_code = "LISTING_EVALUATION_INTERRUPTED"
                existing_run.finished_at = now
                session.commit()
            if existing_run is not None:
                if existing_run.attempt_count >= 3:
                    return
                if (
                    existing_run.last_dispatch_at is not None
                    and existing_run.last_dispatch_at > now - timedelta(minutes=15)
                ):
                    return
            # Each failed/partial attempt is retained; retries are rate-limited.
            run_id = ListingEvaluationBatchService(session).run_daily_diagnostic(
                schedule_date_cn=local.date(),
                cutoff_date_la=rating_cutoff_la(now),
                batch_size=50,
            )
            if get_settings().listing_evaluation_publish_enabled:
                ListingEvaluationPublisher(session).publish_run(run_id=run_id)
                ListingEvaluationBatchService(session).create_followups_for_published_run(
                    run_id=run_id
                )
        finally:
            session.execute(text("SELECT pg_advisory_unlock(2406251026)"))
