"""Opt-in, no-secret Celery dispatch for durable Walmart remote jobs."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.celery_app import INTEGRATION_QUEUE, celery_app
from app.db.session import get_session_factory
from app.integrations.walmart.remote_pipeline import collect_store_read_only
from app.modules.walmart_remote.models import WalmartRemoteJob


@celery_app.task(name="walmart_remote.execute", ignore_result=True)  # type: ignore[misc]
def execute_remote_job(job_id: str) -> None:
    """Only job ID in Celery; no token, credentials or data in broker/results."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        return
    job_uuid = UUID(job_id)
    with get_session_factory()() as session:
        job = session.scalar(
            select(WalmartRemoteJob).where(WalmartRemoteJob.id == job_uuid).with_for_update()
        )
        if job is None or job.status != "queued":
            return
        store_code = job.store_code
        operations = tuple(job.operations)
        run_id = "wmt-" + job.id.hex
        job.run_id = run_id
        job.status = "running"
        job.started_at = datetime.now(UTC)
        session.commit()
    try:
        archive_path = os.getenv("SZZSBJ_WALMART_REMOTE_ARCHIVE_ROOT", "")
        if not archive_path or not Path(archive_path).is_absolute():
            raise ValueError("REMOTE_ARCHIVE_NOT_CONFIGURED")
        result = collect_store_read_only(
            store_code=store_code,
            operations=operations,
            archive_root=Path(archive_path),
            run_id=run_id,
        )
        error_code = None
    except Exception:
        result = None
        error_code = "WALMART_REMOTE_EXECUTION_FAILED"
    with get_session_factory()() as session:
        job = session.scalar(
            select(WalmartRemoteJob).where(WalmartRemoteJob.id == job_uuid).with_for_update()
        )
        if job is None or job.status != "running" or job.run_id != run_id:
            return
        job.status = "succeeded" if result else "failed"
        job.error_code = error_code
        job.files_verified = result["files_verified"] if result else None
        job.finished_at = datetime.now(UTC)
        session.commit()


def dispatch_remote_job(job_id: UUID) -> None:
    """Celery stores only the opaque UUID; strictly opt-in."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        raise ValueError("REMOTE_COLLECTION_DISABLED")
    execute_remote_job.apply_async(
        args=(str(job_id),), queue=INTEGRATION_QUEUE, routing_key=INTEGRATION_QUEUE
    )
