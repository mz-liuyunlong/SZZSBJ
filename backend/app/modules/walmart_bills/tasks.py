"""沃尔玛对账报表打款额：Celery 任务（默认不排期；SZZSBJ_WALMART_RECON_PAYOUT_ENABLED=1 才跑）。

页面「拉沃尔玛打款额」和 Beat 都只投递这个任务；凭据、token 不进 Celery。
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.modules.walmart_bills.recon_payout_sync import (
    enabled,
    production_call,
    production_store_codes,
    sync_recon_payouts,
)

log = logging.getLogger(__name__)

TASK_NAME = "walmart_bills.recon_payout_sync"


class ReconPayoutDispatchError(RuntimeError):
    pass


def dispatch_recon_payout_sync() -> None:
    """页面按钮投递；任务本身再检查开关。"""
    from app.celery_app import INTEGRATION_QUEUE

    try:
        recon_payout_sync_task.apply_async(queue=INTEGRATION_QUEUE, routing_key=INTEGRATION_QUEUE)
    except Exception:
        raise ReconPayoutDispatchError("task dispatch is unavailable") from None


@celery_app.task(name=TASK_NAME, ignore_result=True)  # type: ignore[misc]
def recon_payout_sync_task() -> None:
    if not enabled():
        log.info("walmart recon payout sync disabled")
        return
    with get_session_factory()() as session:
        result = sync_recon_payouts(
            session, call=production_call(), store_codes=production_store_codes()
        )
        session.commit()
    log.info(
        "walmart recon payout sync: written=%s failed=%s",
        result.written,
        ",".join(result.failed) or "-",
    )
