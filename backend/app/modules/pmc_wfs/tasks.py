"""Load explicitly with Celery -I app.modules.pmc_wfs.tasks; no shared schedule edits.

Read-backs while a shipment is 提交中 are re-queued by the task itself (countdown 180 s,
at most 10), so no beat schedule is needed.
"""

from celery import shared_task

from app.db.session import get_session_factory
from app.modules.pmc_wfs.creation_worker import run_operation
from app.modules.pmc_wfs.gateway import get_creation_gateway


@shared_task(name="integration_sync.wfs_creation", acks_late=True, reject_on_worker_lost=True)
def execute_operation(operation_id, action="execute"):
    run_operation(
        get_session_factory(), get_creation_gateway(), operation_id, action, schedule=schedule
    )


def schedule(operation_id, action, countdown):
    execute_operation.apply_async(
        args=[operation_id, action], queue="integration", countdown=countdown
    )


def dispatch_creation(operation_id, action="execute"):
    execute_operation.apply_async(args=[operation_id, action], queue="integration")


def get_creation_dispatcher():
    return dispatch_creation
