"""LA calendar scheduling: DST, prior completed day, and retry invariants."""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.celery_app import INTEGRATION_QUEUE, create_celery_app
from app.modules.clearance_center.daily import daily_window, is_midnight_window


def test_midnight_trigger_switches_utc_offset_on_spring_dst() -> None:
    before = datetime(2026, 3, 8, 8, 0, tzinfo=UTC)
    after = datetime(2026, 3, 9, 7, 0, tzinfo=UTC)
    assert is_midnight_window(before)
    assert is_midnight_window(after)
    assert daily_window(before) == (date(2026, 3, 8), date(2026, 3, 7))
    assert daily_window(after) == (date(2026, 3, 9), date(2026, 3, 8))


def test_midnight_trigger_switches_utc_offset_on_fall_dst() -> None:
    before = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    after = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    assert is_midnight_window(before)
    assert is_midnight_window(after)
    assert daily_window(before) == (date(2026, 11, 1), date(2026, 10, 31))
    assert daily_window(after) == (date(2026, 11, 2), date(2026, 11, 1))


def test_task_only_starts_at_midnight_local_hour() -> None:
    assert not is_midnight_window(datetime(2026, 11, 4, 7, 59, tzinfo=UTC))
    assert is_midnight_window(datetime(2026, 11, 4, 8, 0, tzinfo=UTC))
    assert not is_midnight_window(datetime(2026, 11, 4, 9, 0, tzinfo=UTC))


def test_beat_task_registered_to_existing_governed_queue() -> None:
    celery = create_celery_app(broker_url="memory://")
    assert "app.modules.clearance_center.tasks" in celery.conf.include
    assert celery.conf.task_routes["clearance_center.*"]["queue"] == INTEGRATION_QUEUE
    assert celery.conf.beat_schedule["clearance-daily-los-angeles"]["task"] == (
        "clearance_center.scheduler_tick"
    )
