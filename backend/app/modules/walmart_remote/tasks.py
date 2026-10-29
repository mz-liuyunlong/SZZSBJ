"""Opt-in, no-secret Celery dispatch for durable Walmart remote jobs."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.celery_app import INTEGRATION_QUEUE, celery_app
from app.db.session import get_session_factory
from app.integrations.walmart.remote_dispatch import DispatchRejected, parse_routes
from app.integrations.walmart.remote_recovery import recover_completed_run
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
        source_account_ref = job.source_account_ref
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
            job_id=job_uuid,
            source_account_ref=source_account_ref,
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
            "REMOTE_FETCH_TIMEOUT",
            "REMOTE_FETCH_FAILED",
            "REMOTE_FETCH_UNAVAILABLE",
            "REMOTE_ARCHIVE_ALREADY_EXISTS",
            "REMOTE_CLEANUP_UNCONFIRMED",
            "REMOTE_CONVERSION_ALREADY_EXISTS",
            "REMOTE_INGEST_RECEIPT_CONFLICT",
            "REMOTE_INGEST_VERIFICATION_FAILED",
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


@celery_app.task(name="walmart_remote.recover", ignore_result=True)  # type: ignore[misc]
def recover_remote_job(job_id: str) -> None:
    """Only recover an existing run; never request a token or restart Worker."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        return
    with get_session_factory()() as session:
        job = session.scalar(
            select(WalmartRemoteJob).where(WalmartRemoteJob.id == UUID(job_id)).with_for_update()
        )
        if job is None or job.status != "needs_review" or not job.run_id:
            return
        store_code = job.store_code
        store_id = job.store_id
        operations = tuple(job.operations)
        run_id = job.run_id
        job.status = "recovering"
        session.commit()
    try:
        routes = parse_routes(os.getenv("SZZSBJ_WALMART_REMOTE_ROUTES", ""))
        archive_root = Path(os.environ["SZZSBJ_WALMART_REMOTE_ARCHIVE_ROOT"])
        result = recover_completed_run(
            route=routes[store_code],
            store_id=store_id,
            run_id=run_id,
            operations=operations,
            archive_root=archive_root,
            job_id=UUID(job_id),
            source_account_ref=source_account_ref,
        )
    except Exception:
        # No guessing, no worker restart. Preserve remote artifacts and status.
        with get_session_factory()() as session:
            job = session.scalar(
                select(WalmartRemoteJob)
                .where(WalmartRemoteJob.id == UUID(job_id))
                .with_for_update()
            )
            if job is not None and job.status == "recovering" and job.run_id == run_id:
                job.status = "needs_review"
                session.commit()
        return
    with get_session_factory()() as session:
        job = session.scalar(
            select(WalmartRemoteJob).where(WalmartRemoteJob.id == UUID(job_id)).with_for_update()
        )
        if job is None or job.status != "recovering" or job.run_id != run_id:
            return
        job.status = "succeeded"
        job.error_code = None
        job.files_verified = int(result["files_verified"])
        job.finished_at = datetime.now(UTC)
        session.commit()


@celery_app.task(name="walmart_remote.recovery_tick", ignore_result=True)  # type: ignore[misc]
def recovery_tick() -> None:
    """Inspect a bounded number of uncertain runs; no worker restarts or tokens."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        return
    if os.getenv("SZZSBJ_WALMART_REMOTE_RECOVERY_ENABLED") != "1":
        return
    cutoff = datetime.now(UTC) - timedelta(minutes=20)
    with get_session_factory()() as session:
        ids = session.scalars(
            select(WalmartRemoteJob.id)
            .where(
                WalmartRemoteJob.status == "needs_review",
                WalmartRemoteJob.finished_at < cutoff,
                WalmartRemoteJob.run_id.is_not(None),
            )
            .order_by(WalmartRemoteJob.finished_at)
            .limit(20)
        ).all()
    for job_id in ids:
        recover_remote_job.apply_async(
            args=(str(job_id),),
            queue=INTEGRATION_QUEUE,
            routing_key=INTEGRATION_QUEUE,
        )
