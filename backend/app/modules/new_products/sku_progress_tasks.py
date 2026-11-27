"""Production-only projection reconciliation, without remote calls."""

from app.celery_app import celery_app, sku_progress_refresh_enabled
from app.db.session import get_session_factory

from .sku_progress_projection import refresh_sources


@celery_app.task(name="new_products.sku_progress_refresh", ignore_result=True)
def sku_progress_refresh() -> dict:
    if not sku_progress_refresh_enabled():
        return {"status": "disabled"}
    with get_session_factory()() as db, db.begin():
        return refresh_sources(db)
