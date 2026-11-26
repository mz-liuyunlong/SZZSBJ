"""Production-only projection reconciliation, without remote calls."""

import os

from app.celery_app import celery_app
from app.db.session import get_session_factory

from .sku_progress_projection import refresh_sources


@celery_app.task(name="new_products.sku_progress_refresh", ignore_result=True)
def sku_progress_refresh() -> dict:
    if os.getenv("APP_ENV", "").strip().lower() != "production":
        return {"status": "disabled"}
    if os.getenv("SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {"status": "disabled"}
    with get_session_factory()() as db, db.begin():
        return refresh_sources(db)
