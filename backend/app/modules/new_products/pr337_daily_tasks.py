"""One production PR337 nightly master: daily scores -> ads -> trust audit.

Only this task is scheduled. The other task entrypoints remain available for
explicit manual business triggers but are never installed in Beat's schedule.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_engine

from .pr337_daily_db import run_daily

SCHEDULE_FLAG = "SZZSBJ_NEW_PRODUCTS_DAILY_ENABLED"
WRITE_FLAG = "SZZSBJ_NEW_PRODUCTS_DAILY_WRITE_ENABLED"
LA = ZoneInfo("America/Los_Angeles")
LOGGER = logging.getLogger(__name__)


def enabled(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in {"1", "yes", "true", "on"}


@celery_app.task(name="new_products.daily_score_tick", ignore_result=True)
def daily_score_tick() -> dict:
    # SZZSBJ_NEW_PRODUCTS_AUTHORITY_V2: no legacy MART profit writer.
    if (
        os.getenv("APP_ENV", "").strip().lower() == "production"
        and enabled(SCHEDULE_FLAG)
        and enabled(WRITE_FLAG)
    ):
        from .evaluation_workflow import finalize_automatic
        from .unified_publish import execute_unified_job

        unified = execute_unified_job(limit=500, apply=True)
        # The unified publisher has committed its bounded batches. Formal
        # evaluation now checks that saved V2 proof, never reruns the score.
        cutoff = datetime.now(LA).date() - timedelta(days=1)
        with Session(bind=get_engine(), autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                session.execute(text("SELECT set_config('statement_timeout','120000',true)"))
                session.execute(text("SELECT set_config('lock_timeout','3000',true)"))
                formal = finalize_automatic(session, cutoff)
        return {
            "status": "complete",
            "authority": "new_products_authority_v2",
            "unified": unified,
            "automatic_evaluations": formal,
        }
    if os.getenv("APP_ENV", "").strip().lower() != "production" or not enabled(SCHEDULE_FLAG):
        return {"status": "disabled"}
    apply = enabled(WRITE_FLAG)
    cutoff = datetime.now(LA).date() - timedelta(days=1)
    # Stage 1: bounded source proof and guarded score persistence (or read-only preview).
    with Session(bind=get_engine(), autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            level = "REPEATABLE READ" if apply else "REPEATABLE READ READ ONLY"
            session.execute(text("SET TRANSACTION ISOLATION LEVEL " + level))
            session.execute(text("SELECT set_config('statement_timeout','120000',true)"))
            session.execute(text("SELECT set_config('lock_timeout','3000',true)"))
            daily = run_daily(session, apply=apply, cutoff_la=cutoff)
    if not apply:
        return {"status": "dry_run", "cutoff_la": cutoff.isoformat(), "daily": daily}
    # Stage 2: ad display proof only. No scoring evaluation/grade writer here.
    from .pr337_daily_pipeline import publish_daily_ads

    try:
        ads = publish_daily_ads(cutoff=cutoff)
    except Exception as exc:
        # The daily score transaction is already committed. Never erase it
        # because a separate source-read for advertising failed.
        LOGGER.exception("pr337_midnight_ad_evidence_unavailable")
        ads = {"status": "unavailable", "error_type": type(exc).__name__}
    # Stage 3: verify already saved scores from immutable FACT order identities.
    # The trust evidence synchronizer never synthesizes an absent trust score.
    from .trust_evidence_sync import sync_saved_trust_evidence

    cutoff_text = os.getenv("SZZSBJ_NEW_PRODUCT_TRUST_MIN_CALCULATED_AT", "").strip()
    if not cutoff_text:
        raise RuntimeError("TRUST_MIN_CALCULATED_AT_REQUIRED")
    after = datetime.fromisoformat(cutoff_text.replace("Z", "+00:00"))
    if after.tzinfo is None or after.utcoffset() is None:
        raise RuntimeError("TRUST_MIN_CALCULATED_AT_NOT_TIMEZONE_AWARE")
    with Session(bind=get_engine(), autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            trust = sync_saved_trust_evidence(session, after_date=after.astimezone(UTC))
    ad_state = ads.get("catalog_state")
    ad_incomplete = (
        ads.get("status") == "unavailable"
        or ad_state not in {"VERIFIED_LABELS", "VERIFIED_LABELS_WITH_CONFLICTS"}
        or any(
            k.startswith("evidence_") and k != "evidence_complete" and v > 0
            for k, v in ads.items()
            if isinstance(v, int)
        )
    )
    return {
        "status": "partial" if ad_incomplete else "complete",
        "cutoff_la": cutoff.isoformat(),
        "daily": daily,
        "ads": ads,
        "trust_evidence": asdict(trust),
    }
