"""Feature-flagged Celery tick for saved trust evidence; no source writes."""
from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_engine

from .trust_evidence_sync import sync_saved_trust_evidence

ENABLED = "SZZSBJ_NEW_PRODUCT_TRUST_SYNC_ENABLED"
AFTER = "SZZSBJ_NEW_PRODUCT_TRUST_MIN_CALCULATED_AT"


def enabled_from_env() -> datetime | None:
    if os.getenv("APP_ENV", "").strip().lower() != "production":
        return None
    if os.getenv(ENABLED, "").strip().lower() not in {"true", "1", "yes", "on"}:
        return None
    cutoff = os.getenv(AFTER, "").strip()
    if not cutoff:
        return None
    try:
        parsed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    except ValueError:
        return None


@celery_app.task(name="new_products.trust_evidence_sync", ignore_result=True)
def sync_trust_evidence() -> dict[str, int | str]:
    after_date = enabled_from_env()
    if after_date is None:
        return {"status": "disabled"}
    with Session(bind=get_engine(), autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            result = sync_saved_trust_evidence(session, after_date=after_date)
        return {
            "status": "locked" if result.locked else "complete",
            "examined": result.examined,
            "verified": result.verified,
            "written": result.written,
            "skipped": result.skipped,
        }
