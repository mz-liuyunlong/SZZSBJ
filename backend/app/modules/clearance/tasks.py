"""Idempotent clearance data recalculation (never applications or external ads)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.celery_app import celery_app, get_broker_url
from app.db.session import get_engine
from . import service

LA = ZoneInfo("America/Los_Angeles")


@celery_app.task(name="clearance.recalculate", ignore_result=True)
def recalculate() -> dict:
    with Session(get_engine()) as session:
        return service.recalculate_all(session)


@celery_app.task(name="clearance.recalculate_scope", ignore_result=True)
def recalculate_scope(account: str) -> dict:
    if not account or account != account.strip():
        return {"examined": 0, "invalid_scope": True}
    with Session(get_engine()) as session:
        result = service.recalculate_all(session, accounts=frozenset({account}))
        service.batch_reconcile_running(session, accounts=frozenset({account}))
        return result


def enqueue_scope_recalculation(account: str) -> str:
    if get_broker_url() == "memory://":
        recalculate_scope(account)
        return "completed_inline"
    recalculate_scope.delay(account)
    return "queued"


def enqueue_recalculation() -> str:
    # Brokerless development does not have a consumer for memory://; execute
    # inline instead of pretending a task was queued.
    if get_broker_url() == "memory://":
        recalculate()
        return "completed_inline"
    recalculate.delay()
    return "queued"


@celery_app.task(name="clearance.scheduler_tick", ignore_result=True)
def scheduler_tick() -> None:
    today = datetime.now(UTC).astimezone(LA).date()
    engine = get_engine()
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(2406251078)")):
            return
        try:
            with Session(engine) as session:
                old = session.execute(text("""
                    SELECT status FROM biz_clearance_daily_runs
                    WHERE business_date_la=:date
                """), {"date": today}).first()
                if old is not None:
                    return
                version, _ = service.rule_version(session)
                session.execute(text("""
                    INSERT INTO biz_clearance_daily_runs
                        (business_date_la,status,rule_version,examined,started_at)
                    VALUES (:date,'running',:version,0,now())
                    ON CONFLICT (business_date_la) DO NOTHING
                """), {"date": today, "version": version})
                session.commit()
                try:
                    result = service.recalculate_all(session)
                    service.batch_reconcile_running(session)
                    session.execute(text("""
                        UPDATE biz_clearance_daily_runs
                        SET status='succeeded',examined=:examined,finished_at=now()
                        WHERE business_date_la=:date AND status='running'
                    """), {"date": today, "examined": result["examined"]})
                    session.commit()
                except Exception:
                    session.rollback()
                    session.execute(text("""
                        UPDATE biz_clearance_daily_runs
                        SET status='failed',error_code='CLEARANCE_RECALC_FAILED',finished_at=now()
                        WHERE business_date_la=:date AND status='running'
                    """), {"date": today})
                    session.commit()
                    raise
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(2406251078)"))
            lock.commit()
