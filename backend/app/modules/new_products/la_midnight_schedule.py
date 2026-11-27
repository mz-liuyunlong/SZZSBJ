"""Exactly one nightly PR337 Beat schedule in the Los Angeles business timezone.

The rest of the Celery application remains UTC. Convert every Beat timestamp
explicitly to America/Los_Angeles; fixed UTC crontabs drift during DST.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from celery.schedules import schedule

LA = ZoneInfo("America/Los_Angeles")


def _la_now() -> datetime:
    return datetime.now(LA)


class LosAngelesMidnightSchedule(schedule):
    """Run once per LA calendar day, at midnight (with a 10-minute recovery window).

    A last-run timestamp from Celery Beat is UTC; comparing that UTC hour
    directly with Los Angeles clock hours produces incorrect schedule times.
    """

    def __init__(self, run_every=None, relative=False, nowfun=None, app=None):
        super().__init__(
            run_every=timedelta(days=1),
            relative=False,
            nowfun=nowfun or _la_now,
            app=app,
        )

    def remaining_estimate(self, last_run_at: datetime) -> timedelta:
        now = self.now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("LA_MIDNIGHT_REQUIRES_AWARE_NOW")
        now = now.astimezone(LA)
        last = self.maybe_make_aware(last_run_at).astimezone(LA)
        midnight = datetime.combine(now.date(), time.min, tzinfo=LA)
        if last.date() < now.date() and midnight <= now < midnight + timedelta(minutes=10):
            target = midnight
        else:
            target = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=LA)
        return max(timedelta(0), target.astimezone(UTC) - now.astimezone(UTC))
