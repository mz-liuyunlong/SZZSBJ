"""Celery Beat tick for midnight Los Angeles clearance evaluation.

Uses the same integration queue as existing governed internal tasks. This
only evaluates persisted SZZSBJ data and never calls Walmart or creates tasks.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_engine
from app.modules.clearance_center.daily import DailyClearanceEvaluation


@celery_app.task(name="clearance_center.scheduler_tick", ignore_result=True)
def scheduler_tick() -> dict:
    now = datetime.now(UTC)
    # Beat fires every five minutes. The day's first tick is at LA midnight.
    # If Beat/Redis was unavailable then, retry later in the SAME LA day.
    # ops_clearance_daily_runs enforces one successful run per LA date.
    # The advisory lock is session-scoped: pin all transactional batches to
    # one connection until the daily evaluation finishes or fails.
    with get_engine().connect() as connection:
        with Session(bind=connection, autoflush=False, expire_on_commit=False) as session:
            return DailyClearanceEvaluation(session).evaluate_day(now=now, scheduled=False)
