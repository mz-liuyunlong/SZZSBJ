"""Idempotent clearance data recalculation (never applications or external ads)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.celery_app import celery_app, get_broker_url
from app.db.session import get_engine

from . import service

AUTO_FLAG = "SZZSBJ_CLEARANCE_AUTO_ENABLED"


def auto_enabled() -> bool:
    return (
        os.getenv(AUTO_FLAG, "0").strip().lower() in {"1", "true", "on", "yes"}
        and os.getenv("APP_ENV", "").strip().lower() == "production"
    )


def _disabled() -> dict:
    return {"examined": 0, "disabled": True}


LA = ZoneInfo("America/Los_Angeles")


@celery_app.task(name="clearance.recalculate", ignore_result=True)
def recalculate() -> dict:
    if not auto_enabled():
        return _disabled()
    with Session(get_engine()) as session:
        return service.recalculate_all(session)


@celery_app.task(name="clearance.recalculate_scope", ignore_result=True)
def recalculate_scope(account: str) -> dict:
    if not auto_enabled():
        return _disabled()
    if not account or account != account.strip():
        return {"examined": 0, "invalid_scope": True}
    with Session(get_engine()) as session:
        result = service.recalculate_all(session, accounts=frozenset({account}))
        service.batch_reconcile_running(session, accounts=frozenset({account}))
        return result


def enqueue_scope_recalculation(account: str) -> str:
    if not auto_enabled():
        return "disabled"
    if get_broker_url() == "memory://":
        recalculate_scope(account)
        return "completed_inline"
    recalculate_scope.delay(account)
    return "queued"


def enqueue_recalculation() -> str:
    if not auto_enabled():
        return "disabled"
    # Brokerless development does not have a consumer for memory://; execute
    # inline instead of pretending a task was queued.
    if get_broker_url() == "memory://":
        recalculate()
        return "completed_inline"
    recalculate.delay()
    return "queued"


@celery_app.task(name="clearance.scheduler_tick", ignore_result=True)
def scheduler_tick() -> None:
    if not auto_enabled():
        return
    run_daily(retry_failed=False)


def run_daily(*, retry_failed: bool = False) -> dict:
    """Once per Los Angeles date, with explicit retry only for failed runs."""
    today = datetime.now(UTC).astimezone(LA).date()
    engine = get_engine()
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(2406251078)")):
            return {"status": "already_running", "date": str(today)}
        try:
            with Session(engine) as session:
                old = session.execute(
                    text("""
                    SELECT status FROM biz_clearance_daily_runs
                    WHERE business_date_la=:date
                """),
                    {"date": today},
                ).first()
                if old is not None:
                    if old.status == "succeeded" or not (retry_failed and old.status == "failed"):
                        return {"status": old.status, "date": str(today)}
                    session.execute(
                        text("""
                        UPDATE biz_clearance_daily_runs
                        SET status='running',started_at=now(),finished_at=NULL,
                            error_code=NULL,examined=0
                        WHERE business_date_la=:date AND status='failed'
                    """),
                        {"date": today},
                    )
                version, _ = service.rule_version(session, require_persisted=True)
                session.execute(
                    text("""
                    INSERT INTO biz_clearance_daily_runs
                        (business_date_la,status,rule_version,examined,started_at)
                    VALUES (:date,'running',:version,0,now())
                    ON CONFLICT (business_date_la) DO NOTHING
                """),
                    {"date": today, "version": version},
                )
                session.commit()
                try:
                    result = service.recalculate_all(session)
                    service.batch_reconcile_running(session)
                    session.execute(
                        text("""
                        UPDATE biz_clearance_daily_runs
                        SET status='succeeded',examined=:examined,finished_at=now()
                        WHERE business_date_la=:date AND status='running'
                    """),
                        {"date": today, "examined": result["examined"]},
                    )
                    session.commit()
                    return {"status": "succeeded", "date": str(today), **result}
                except Exception as exc:
                    session.rollback()
                    session.execute(
                        text("""
                        UPDATE biz_clearance_daily_runs
                        SET status='failed',error_code=:error_code,finished_at=now()
                        WHERE business_date_la=:date AND status='running'
                    """),
                        {
                            "date": today,
                            "error_code": ("CLEARANCE_RECALC_" + type(exc).__name__.upper())[:128],
                        },
                    )
                    session.commit()
                    raise
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(2406251078)"))
            lock.commit()
