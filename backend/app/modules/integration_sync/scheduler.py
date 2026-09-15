from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery.schedules import ParseException, crontab
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunEvent
from app.modules.integration_sync.repository import IntegrationSyncRepository

CRON_SEARCH_DAYS = 40 * 366
QUEUED_RECOVERY_GRACE = timedelta(minutes=1)


class ScheduleExpressionError(ValueError):
    "Safe invalid-schedule error without echoing the cron expression."


def validate_cron_expression(expression: str) -> None:
    _parse_cron(expression)


def next_cron_instant(expression: str, after: datetime) -> datetime:
    "Return the first UTC cron instant strictly after ``after``."
    if after.utcoffset() is None:
        raise ScheduleExpressionError("SYNC_SCHEDULE_TIMEZONE_INVALID")

    schedule = _parse_cron(expression)
    reference = after.astimezone(UTC)
    minutes = sorted(int(value) for value in schedule.minute)
    hours = sorted(int(value) for value in schedule.hour)
    days_of_week = {int(value) for value in schedule.day_of_week}
    days_of_month = {int(value) for value in schedule.day_of_month}
    months = {int(value) for value in schedule.month_of_year}

    start_date = reference.date()
    for day_offset in range(CRON_SEARCH_DAYS):
        candidate_date = start_date + timedelta(days=day_offset)
        celery_weekday = (candidate_date.weekday() + 1) % 7
        if (
            candidate_date.month not in months
            or candidate_date.day not in days_of_month
            or celery_weekday not in days_of_week
        ):
            continue
        for hour in hours:
            for minute in minutes:
                candidate = datetime(
                    candidate_date.year,
                    candidate_date.month,
                    candidate_date.day,
                    hour,
                    minute,
                    tzinfo=UTC,
                )
                if candidate > reference:
                    return candidate

    raise ScheduleExpressionError("SYNC_SCHEDULE_HAS_NO_FUTURE_INSTANT")


def _parse_cron(expression: str) -> crontab:
    normalized = expression.strip()
    if not normalized or len(normalized) > 128:
        raise ScheduleExpressionError("SYNC_SCHEDULE_CRON_INVALID")
    try:
        return crontab.from_string(normalized)
    except (ParseException, TypeError, ValueError):
        raise ScheduleExpressionError("SYNC_SCHEDULE_CRON_INVALID") from None


class IntegrationSchedulerService:
    "Bounded UTC scheduler with durable next-run advancement."

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def recoverable_queued_run_ids(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[UUID]:
        if not 1 <= limit <= 100:
            raise ValueError("scheduler recovery batch limit is invalid")
        current = now or datetime.now(UTC)
        if current.utcoffset() is None:
            raise ValueError("scheduler recovery now must be timezone-aware")
        current = current.astimezone(UTC)
        return self.repository.list_recoverable_queued_run_ids(
            current - QUEUED_RECOVERY_GRACE,
            limit=limit,
        )

    def create_due_runs(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[UUID]:
        if not 1 <= limit <= 100:
            raise ValueError("scheduler batch limit is invalid")

        current = now or datetime.now(UTC)
        if current.utcoffset() is None:
            raise ValueError("scheduler now must be timezone-aware")
        current = current.astimezone(UTC)

        configs = self.repository.list_due_configs(current, limit=limit)
        run_ids: list[UUID] = []
        try:
            for config in configs:
                scheduled_for = config.next_run_at
                if scheduled_for is None:
                    continue

                interface = self.repository.get_interface(config.interface_id)
                if (
                    interface is not None
                    and interface.provider == "lingxing"
                    and interface.interface_key == "productList"
                ):
                    # ProductList is permanently manual-only. Short-circuit
                    # before reading schedule fields so stale schedule rows
                    # cannot make it schedulable or break the scheduler tick.
                    config.next_run_at = None
                    continue

                schedule_cron = config.schedule_cron
                if config.schedule_timezone != "UTC" or not schedule_cron:
                    config.next_run_at = None
                    continue

                try:
                    reference = max(scheduled_for.astimezone(UTC), current)
                    next_run_at = next_cron_instant(schedule_cron, reference)
                except ScheduleExpressionError:
                    config.next_run_at = None
                    continue

                if interface is None or not interface.outbound_enabled:
                    config.next_run_at = next_run_at
                    continue

                key = f"schedule:{config.id}:{scheduled_for.astimezone(UTC).isoformat()}"
                existing = self.repository.find_run_by_idempotency(key)
                if existing is None:
                    run = IntegrationSyncRun(
                        config_id=config.id,
                        interface_id=interface.id,
                        provider=interface.provider,
                        interface_key=interface.interface_key,
                        source_account_ref=config.source_account_ref,
                        trigger_type="schedule",
                        status="queued",
                        idempotency_key=key,
                        reason="scheduled_sync",
                        queued_at=current,
                        work_items_total=0,
                        work_items_succeeded=0,
                        work_items_failed=0,
                        records_seen=0,
                        records_written=0,
                    )
                    self.repository.add_run(run)
                    self.repository.add_event(
                        IntegrationSyncRunEvent(
                            run_id=run.id,
                            sequence_no=1,
                            event_type="state_transition",
                            from_status=None,
                            to_status="queued",
                            message_code="SYNC_RUN_QUEUED",
                            safe_details=None,
                            occurred_at=current,
                            actor_ref="scheduler",
                        )
                    )
                    run_ids.append(run.id)

                config.last_scheduled_at = current
                config.next_run_at = next_run_at

            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return run_ids
