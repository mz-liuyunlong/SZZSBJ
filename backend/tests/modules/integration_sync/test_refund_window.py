"""Date-window regression coverage, including UTC/LA boundary and DST."""

from datetime import UTC, date, datetime

import pytest

from app.modules.integration_sync.refund_window import refund_window


def test_three_day_window():
    start, end = refund_window(datetime(2026, 10, 27, 10, 25, tzinfo=UTC), 3)
    assert (start.date(), end.date()) == (date(2026, 10, 25), date(2026, 10, 27))
    assert start.hour == 0 and end.hour == 23


@pytest.mark.parametrize("days", [None, 0, 15])
def test_legacy_default(days):
    start, end = refund_window(datetime(2026, 10, 27, 10, tzinfo=UTC), days)
    assert (end.date() - start.date()).days == 6


def test_la_date_not_utc_date():
    start, end = refund_window(datetime(2026, 10, 28, 2, tzinfo=UTC), 1)
    assert start.date() == end.date() == date(2026, 10, 27)


def test_dst_dates():
    start, end = refund_window(datetime(2026, 11, 2, 12, tzinfo=UTC), 3)
    assert start.date() == date(2026, 10, 31)
    assert end.date() == date(2026, 11, 2)


def test_naive_rejected():
    with pytest.raises(ValueError):
        refund_window(datetime(2026, 10, 27), 3)
