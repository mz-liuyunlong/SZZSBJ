"""Feature-flagged China-time scheduler for Listing diagnostic snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID
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


@celery_app.task(name="listing_lifecycle.scheduler_tick", ignore_result=True)
def lifecycle_scheduler_tick() -> None:
    """Daily T-2 lifecycle publisher; fully opt-in and independent of grading.

    Connection-scoped advisory lock lives on a dedicated connection. Business
    mutations run in a separate engine-bound Session whose commits are real.
    """
    settings = get_settings()
    if not settings.listing_lifecycle_auto_enabled:
        return
    if settings.app_env == "production" and not settings.listing_lifecycle_production_approved:
        return

    now = datetime.now(UTC)
    local = now.astimezone(CHINA_TZ)
    import json

    from app.modules.listing_rule_config.automation import (
        process_lifecycle_batch,
        verify_schema,
    )

    engine = get_engine()
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(text("SELECT pg_try_advisory_lock(2406251074)"))
        if not acquired:
            return
        try:
            # The independent session is not enlisted in lock_connection's
            # implicit transaction. Every session.commit() is durable.
            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                rule_row = session.scalar(
                    select(ListingGradeRuleVersion)
                    .where(ListingGradeRuleVersion.effective_from <= now)
                    .order_by(ListingGradeRuleVersion.version.desc())
                    .limit(1)
                )
                if not rule_is_due(rule_row, now):
                    return
                config = (
                    ListingGradeRuleConfig.model_validate(rule_row.config_json)
                    if rule_row is not None
                    else ListingGradeRuleConfig()
                )
                version = rule_row.version if rule_row is not None else 0
                cutoff = rating_cutoff_la(now)
                verify_schema(session)
                existing = (
                    session.execute(
                        text("""
                    SELECT status, cutoff_date_la
                    FROM biz_listing_lifecycle_auto_runs
                    WHERE schedule_date_cn=:today
                """),
                        {"today": local.date()},
                    )
                    .mappings()
                    .first()
                )
                if existing is not None:
                    # Failed jobs are not retried unattended without evidence.
                    return
                session.execute(
                    text("""
                    INSERT INTO biz_listing_lifecycle_auto_runs (
                        schedule_date_cn, cutoff_date_la, status, rule_version, started_at
                    ) VALUES (:today, :cutoff, 'running', :version, :now)
                """),
                    {
                        "today": local.date(),
                        "cutoff": cutoff,
                        "version": version,
                        "now": now,
                    },
                )
                session.commit()
                try:
                    result = process_lifecycle_batch(
                        session,
                        cutoff=cutoff,
                        config=config,
                        rule_version=version,
                        dry_run=False,
                    )
                    session.execute(
                        text("""
                        UPDATE biz_listing_lifecycle_auto_runs
                        SET status='succeeded', examined=:examined, updated=:updated,
                            unchanged=:unchanged, skipped=:skipped,
                            skipped_reasons_json=CAST(:reasons AS jsonb),
                            finished_at=:now
                        WHERE schedule_date_cn=:today AND status='running'
                    """),
                        {
                            "examined": result.examined,
                            "updated": result.updated,
                            "unchanged": result.unchanged,
                            "skipped": result.skipped,
                            "reasons": json.dumps(result.skipped_reasons),
                            "today": local.date(),
                            "now": datetime.now(UTC),
                        },
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    session.execute(
                        text("""
                        UPDATE biz_listing_lifecycle_auto_runs
                        SET status='failed', error_code='LIFECYCLE_AUTO_EXECUTION_FAILED',
                            finished_at=:now
                        WHERE schedule_date_cn=:today
                    """),
                        {"today": local.date(), "now": datetime.now(UTC)},
                    )
                    session.commit()
                    raise
        finally:
            # pg_advisory_unlock must run on the connection that acquired it.
            lock_connection.execute(text("SELECT pg_advisory_unlock(2406251074)"))
            lock_connection.commit()


@celery_app.task(name="listing_evaluation.publish_grade_run", ignore_result=False)
def publish_grade_run(run_id: str) -> dict[str, int]:
    """Explicit one-shot publication only; never registered in beat schedules.

    Each daily input must contain reconciled finance + advertising provenance.
    A missing upstream proof blocks publication rather than guessing zero ads.
    """
    from app.modules.listing_rule_config.grade_publication import (
        ListingGradePublicationService,
    )

    if not get_settings().listing_evaluation_publish_enabled:
        raise RuntimeError("LISTING_GRADE_PUBLICATION_NOT_ENABLED")
    with Session(bind=get_engine(), autoflush=False, expire_on_commit=False) as session:
        result = ListingGradePublicationService(session).publish_run(run_id=UUID(run_id))
        return {
            "examined": result.examined,
            "published": result.published,
            "blocked": result.blocked,
            "already_published": result.already_published,
        }
