"""结算利润 V3：订单审核重算的 Celery 任务（§8.1 触发）。

沃尔玛账单同步成功后由执行层投递，只重算本次同步店铺有明细的期（内容没变不写新版本）；
发货单 / 明细 / 出库单 / 成本计价流水同步成功后的触发下一步接入。
页面「重算」走接口同步执行，不经这里。不排 Beat，没有真实外部调用。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.modules.settlement_profit.order_review.calc import (
    OrderReviewCalculator,
    periods_for_recalc,
)

log = logging.getLogger(__name__)

TASK_NAME = "settlement_profit.order_review_recalc"
SOURCE_REF = "primary"


def dispatch_order_review_recalc(store_ids: Iterable[str] = (), *, reason: str = "") -> bool:
    """投递失败不影响调用方（同步本身已成功），只记日志。"""
    from app.celery_app import INTEGRATION_QUEUE

    try:
        order_review_recalc_task.apply_async(
            kwargs={"store_ids": sorted({s for s in store_ids if s}), "reason": reason},
            queue=INTEGRATION_QUEUE,
            routing_key=INTEGRATION_QUEUE,
        )
    except Exception:
        log.warning("order review recalc dispatch failed (%s)", reason or "-")
        return False
    return True


@celery_app.task(name=TASK_NAME, ignore_result=True)  # type: ignore[misc]
def order_review_recalc_task(store_ids: list[str] | None = None, reason: str = "") -> None:
    with get_session_factory()() as session:
        pairs = periods_for_recalc(
            session, source_account_ref=SOURCE_REF, store_ids=store_ids or []
        )
        calculator = OrderReviewCalculator(session, source_account_ref=SOURCE_REF)
        done = skipped = failed = 0
        for store_id, period_key in pairs:
            # 一期出错不拖垮整个任务：回滚这一期、记日志、继续下一期
            try:
                result = calculator.recalc_period(store_id, period_key)
                session.commit()
            except Exception:
                session.rollback()
                failed += 1
                log.exception("order review recalc failed for one period (%s)", period_key)
                continue
            if result.status == "calculated":
                done += 1
            else:
                skipped += 1
    log.info(
        "order review recalc (%s): periods=%s calculated=%s skipped=%s failed=%s",
        reason or "-",
        len(pairs),
        done,
        skipped,
        failed,
    )
