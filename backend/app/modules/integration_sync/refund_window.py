"""Immutable Los Angeles refund windows at enqueue time.

Legacy DATA-PAGES max_pages currently denotes a day count; retain it until a
separate lookback-days migration has been reviewed.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

LA_TZ = ZoneInfo("America/Los_Angeles")


def refund_window(now: datetime, configured_days: int | None) -> tuple[datetime, datetime]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("refund window requires an aware instant")
    days = configured_days if configured_days is not None and 1 <= configured_days <= 14 else 7
    last_day = now.astimezone(LA_TZ).date()
    first_day = last_day - timedelta(days=days - 1)
    return (
        datetime.combine(first_day, time.min, tzinfo=LA_TZ),
        datetime.combine(last_day, time.max, tzinfo=LA_TZ),
    )
