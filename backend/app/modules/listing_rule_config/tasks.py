"""Feature-flagged China-time scheduler for Listing diagnostic snapshots."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.evaluation import rating_cutoff_la
from app.modules.listing_rule_config.models import ListingEvaluationRun, ListingGradeRuleVersion
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CHINA_TZ = ZoneInfo("Asia/Shanghai")


@celery_app.task(name="listing_evaluation.scheduler_tick", ignore_result=True)
def scheduler_tick() -> None:
    """Run only when explicitly enabled and at the saved China-time minute."""
    if not get_settings().listing_evaluation_scheduler_enabled:
        return
    now = datetime.now(UTC)
    local = now.astimezone(CHINA_TZ)
    with get_session_factory()() as session:
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
            config = (
                ListingGradeRuleConfig.model_validate(row.config_json)
                if row is not None
                else ListingGradeRuleConfig()
            )
            if local.strftime("%H:%M") < config.execution_time:
                return
            if (
                session.scalar(
                    select(ListingEvaluationRun.id).where(
                        ListingEvaluationRun.schedule_date_cn == local.date()
                    )
                )
                is not None
            ):
                return
            # The run has a unique China date; only diagnostic snapshots are written.
            ListingEvaluationBatchService(session).run_daily_diagnostic(
                schedule_date_cn=local.date(),
                cutoff_date_la=rating_cutoff_la(now),
                batch_size=50,
            )
        finally:
            session.execute(text("SELECT pg_advisory_unlock(2406251026)"))
