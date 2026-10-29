"""Offline schedule gate tests. No database or external calls."""

from datetime import UTC, datetime

from app.modules.walmart_remote.schedule import eligible_schedule


def test_twice_weekly_pacific_schedule():
    assert eligible_schedule(datetime(2026, 10, 28, 16, 0, tzinfo=UTC)) == "20261028"
    assert eligible_schedule(datetime(2026, 10, 31, 16, 0, tzinfo=UTC)) == "20261031"
    assert eligible_schedule(datetime(2026, 10, 29, 16, 0, tzinfo=UTC)) is None
    assert eligible_schedule(datetime(2026, 10, 28, 15, 0, tzinfo=UTC)) is None
