"""Feature-flagged China-time scheduler for Listing diagnostic snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_engine
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.evaluation import rating_cutoff_la
from app.modules.listing_rule_config.models import ListingEvaluationRun, ListingGradeRuleVersion
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CHINA_TZ = ZoneInfo("Asia/Shanghai")


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
                .order_by(ListingGradeRuleVersion.version.desc())
                .limit(1)
            )
            # A newly saved schedule supersedes the prior schedule immediately,
            # while its explicit boundary prevents an earlier catch-up run.
            if not rule_is_due(row, now):
                return
            existing_run = session.scalar(
                select(ListingEvaluationRun).where(
                    ListingEvaluationRun.schedule_date_cn == local.date()
                )
            )
            if existing_run is not None and existing_run.status in {
                "queued",
                "running",
                "succeeded",
                "partial",
            }:
                return
            if existing_run is not None:
                if existing_run.attempt_count >= 3:
                    return
                if (
                    existing_run.last_dispatch_at is not None
                    and existing_run.last_dispatch_at > now - timedelta(minutes=15)
                ):
                    return
            # The run has a unique China date; failed attempts are rate-limited.
            ListingEvaluationBatchService(session).run_daily_diagnostic(
                schedule_date_cn=local.date(),
                cutoff_date_la=rating_cutoff_la(now),
                batch_size=50,
            )
        finally:
            session.execute(text("SELECT pg_advisory_unlock(2406251026)"))
