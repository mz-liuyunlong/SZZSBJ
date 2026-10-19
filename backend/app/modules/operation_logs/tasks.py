"""Disabled-by-default follow-up sync from the existing new-DB mirror."""

from __future__ import annotations

import os

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.modules.operation_logs.service import import_history


def _active() -> bool:
    return all(
        os.getenv(k) == "true"
        for k in (
            "OPERATION_LOG_MIRROR_SYNC_ENABLED",
            "OPERATION_LOG_HISTORICAL_IMPORT_VERIFIED",
            "OPERATION_LOG_DB_WRITE_AUTHORIZED",
        )
    ) and (
        os.getenv("APP_ENV") != "production"
        or os.getenv("PRODUCTION_LOG_IMPORT_AUTHORIZED") == "true"
    )


@celery_app.task(name="operation_logs.mirror_incremental", ignore_result=True)
def incremental() -> dict[str, int | str]:
    if not _active():
        return {"status": "disabled"}
    with get_session_factory()() as session:
        return import_history(session, commit=True, incremental=True, include_manual=False)


@celery_app.task(name="operation_logs.mirror_reconcile", ignore_result=True)
def reconcile() -> dict[str, int | str]:
    if not _active():
        return {"status": "disabled"}
    with get_session_factory()() as session:
        return import_history(session, commit=True, incremental=False, include_manual=False)
