"""LA calendar scheduling: DST, prior completed day, and retry invariants."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.celery_app import INTEGRATION_QUEUE, create_celery_app
from app.modules.clearance_center.daily import daily_window, is_midnight_window
from app.modules.clearance_center.repository import evaluation_run_status
from app.modules.clearance_center.service import ClearanceService


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


def test_midnight_hour_is_identified_in_los_angeles() -> None:
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


def test_daily_readiness_rejects_prior_day_run() -> None:
    current = date(2026, 11, 4)
    assert evaluation_run_status(current, today=current) == "ready"
    assert evaluation_run_status(date(2026, 11, 3), today=current) == "stale"
    assert evaluation_run_status(date(2026, 11, 5), today=current) == "stale"


def test_scheduler_retries_missed_midnight_without_requiring_the_first_hour(
    monkeypatch,
) -> None:
    from app.modules.clearance_center import tasks

    class FixedDateTime:
        @staticmethod
        def now(_timezone):
            # LA local 09:00 in winter: must still be allowed to recover a missed run.
            return datetime(2026, 11, 4, 17, 0, tzinfo=UTC)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEvaluator:
        def __init__(self, _session):
            pass

        def evaluate_day(self, *, now, scheduled):
            return {"status": "checked", "scheduled": scheduled, "now": now}

    monkeypatch.setattr(tasks, "datetime", FixedDateTime)
    monkeypatch.setattr(tasks, "get_engine", FakeEngine)
    monkeypatch.setattr(tasks, "Session", FakeSession)
    monkeypatch.setattr(tasks, "DailyClearanceEvaluation", FakeEvaluator)
    result = tasks.scheduler_tick()
    assert result["status"] == "checked"
    assert result["scheduled"] is False
    assert result["now"] == datetime(2026, 11, 4, 17, 0, tzinfo=UTC)


def test_stale_daily_run_never_exposes_old_auto_candidates() -> None:
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    previous = today - timedelta(days=1)

    class SnapshotRepository:
        def latest_completed_run(self):
            return {
                "id": "not-read",
                "run_date_la": previous,
                "as_of_date_la": previous - timedelta(days=1),
            }

        def manual_eligible_page(self, _accounts, *, store_id, page, page_size):
            return {"total": 2}

        def snapshot_page(self, *_args, **_kwargs):
            raise AssertionError("Stale risk snapshots must never be served as current")

        def daily_summary(self, *_args, **_kwargs):
            raise AssertionError("Stale risk counts must never be displayed as current")

    service = ClearanceService.__new__(ClearanceService)
    service.repo = SnapshotRepository()
    allowed = frozenset({"allowed-account"})
    listing_page = service.list_listings(allowed)
    assert listing_page["evaluation_status"] == "stale"
    assert listing_page["total"] == 0
    assert listing_page["items"] == []
    summary = service.summary(allowed)
    assert summary["evaluation_status"] == "stale"
    assert summary["high"] == summary["medium"] == 0
    assert summary["eligible_manual"] == 2
