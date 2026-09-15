import logging
from uuid import UUID

from celery import shared_task

import app.modules.media_assets.tasks  # noqa: F401
from app.db.session import get_session_factory
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.scheduler import IntegrationSchedulerService

logger = logging.getLogger("app.integration_sync.tasks")


class TaskDispatchError(RuntimeError):
    """Safe queue-dispatch failure without broker details."""


@shared_task(name="integration_sync.execute_sync_run", ignore_result=True)  # type: ignore[untyped-decorator]
def execute_sync_run(run_id: str) -> None:
    parsed_run_id = UUID(run_id)
    with get_session_factory()() as session:
        SyncRunExecutionService(session).execute(parsed_run_id)


@shared_task(name="integration_sync.scheduler_tick", ignore_result=True)  # type: ignore[untyped-decorator]
def scheduler_tick() -> None:
    with get_session_factory()() as session:
        scheduler = IntegrationSchedulerService(session)
        new_run_ids = scheduler.create_due_runs()
        recovery_run_ids = scheduler.recoverable_queued_run_ids()

    run_ids = list(dict.fromkeys((*new_run_ids, *recovery_run_ids)))
    for run_id in run_ids:
        try:
            dispatch_sync_run(run_id)
        except TaskDispatchError:
            # The durable run remains queued. A later scheduler tick will pick
            # it up after the recovery grace window.
            logger.warning("integration_sync_dispatch_deferred run_id=%s", run_id)


def dispatch_sync_run(run_id: UUID) -> None:
    try:
        execute_sync_run.delay(str(run_id))
    except Exception:
        raise TaskDispatchError("task dispatch is unavailable") from None
