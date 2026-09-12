from uuid import UUID

from celery import shared_task

from app.db.session import get_session_factory
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.scheduler import IntegrationSchedulerService


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
        run_ids = IntegrationSchedulerService(session).create_due_runs()
    for run_id in run_ids:
        dispatch_sync_run(run_id)


def dispatch_sync_run(run_id: UUID) -> None:
    try:
        execute_sync_run.delay(str(run_id))
    except Exception:
        raise TaskDispatchError("task dispatch is unavailable") from None
