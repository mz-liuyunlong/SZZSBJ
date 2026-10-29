"""Opt-in, no-secret Celery dispatch for durable Walmart remote jobs."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.celery_app import INTEGRATION_QUEUE, celery_app
from app.db.session import get_session_factory
from app.integrations.walmart.remote_dispatch import DispatchRejected
from app.integrations.walmart.remote_pipeline import collect_store_read_only
from app.modules.walmart_remote.models import WalmartRemoteJob
from app.modules.walmart_remote.schedule import queue_due_stores


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
        store_id = job.store_id
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
            store_id=store_id,
            operations=operations,
            archive_root=Path(archive_path),
            run_id=run_id,
        )
        error_code = None
    except DispatchRejected as exc:
        result = None
        error_code = str(exc)
    except Exception:
        result = None
        error_code = "WALMART_REMOTE_EXECUTION_FAILED"
    with get_session_factory()() as session:
        job = session.scalar(
            select(WalmartRemoteJob).where(WalmartRemoteJob.id == job_uuid).with_for_update()
        )
        if job is None or job.status != "running" or job.run_id != run_id:
            return
        uncertain = error_code in {
            "REMOTE_WORKER_UNCONFIRMED",
            "REMOTE_ALREADY_UNKNOWN",
            "REMOTE_ALREADY_RUNNING",
        }
        job.status = "succeeded" if result else "needs_review" if uncertain else "failed"
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


@celery_app.task(name="walmart_remote.scheduler_tick", ignore_result=True)  # type: ignore[misc]
def scheduler_tick() -> None:
    """Periodic scheduling; never passes Walmart credentials into Celery."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_SCHEDULE_ENABLED") != "1":
        return
    with get_session_factory()() as session:
        job_ids = queue_due_stores(session, now=datetime.now(UTC))
        session.commit()
    for job_id in job_ids:
        execute_remote_job.apply_async(
            args=(job_id,),
            queue=INTEGRATION_QUEUE,
            routing_key=INTEGRATION_QUEUE,
        )
