"""结算利润 V3：订单审核重算的投递与 Celery 任务（§8.1 触发；#377 终审改为按范围 + 队列）。

- 沃尔玛账单同步：只投递本次同步成功的店铺有明细的期（dispatch_order_review_recalc）。
- 发货单 / 发货单明细 / 出库单 / 成本计价流水同步：执行层只投递内容真的变了的行所在的期
  （enqueue_affected）。
- 投递 = 写进重算队列 settlement_recalc_queue（去重），再踢一下任务；任务把队列扫空为止，
  同一期同一时刻只有一个在算。
- 恢复路径（#377 终审 P1-01）：任务扫完队列里仍有可取的行（到上限、或算的时候又进来）就再踢自己
  一次；踢任务失败只是少一次触发，队列行已提交，Beat 每 10 分钟的 sweep
  （settlement_profit.order_review_recalc_sweep）有可取的行才扫，最迟 10 分钟内补上。
- 同步路径不允许投空范围：空 = 不投递，绝不退回全部店铺。全量重算只能由页面 / 接口
  POST /api/finance/order-review/recalc 显式发起（同步执行，不经这里）。没有外部调用。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.modules.settlement_profit.order_review.calc import (
    OrderReviewCalculator,
    periods_for_recalc,
)
from app.modules.settlement_profit.order_review.recalc_queue import (
    MAX_ITEMS_PER_DRAIN,
    DrainResult,
    drain,
    enqueue,
    has_pending,
)

log = logging.getLogger(__name__)

TASK_NAME = "settlement_profit.order_review_recalc"
SWEEP_TASK_NAME = "settlement_profit.order_review_recalc_sweep"
SOURCE_REF = "primary"


def kick_order_review_recalc(*, reason: str = "") -> bool:
    """踢一下扫队列的任务；投递失败只记日志（队列行已提交，Beat 的 sweep 最迟 10 分钟内扫到）。"""
    from app.celery_app import INTEGRATION_QUEUE

    try:
        order_review_recalc_task.apply_async(
            kwargs={"reason": reason},
            queue=INTEGRATION_QUEUE,
            routing_key=INTEGRATION_QUEUE,
        )
    except Exception:
        log.warning("order review recalc dispatch failed (%s)", reason or "-")
        return False
    return True


def enqueue_affected(
    session: Session, pairs: Iterable[tuple[str, str]], *, reason: str
) -> tuple[int, bool]:
    """把受影响的 (店铺, 账期) 写进队列并提交，再踢任务；返回 (期数, 是否踢成功)。

    没有期就什么都不做，返回 (0, True)。踢失败时队列行已提交，由 sweep 补上；调用方据此记事件。
    """
    count = enqueue(session, source_account_ref=SOURCE_REF, pairs=pairs, reason=reason)
    if count == 0:
        return 0, True
    session.commit()
    return count, kick_order_review_recalc(reason=reason)


def dispatch_order_review_recalc(store_ids: Iterable[str] = (), *, reason: str = "") -> bool:
    """账单同步后：只重算这些店铺有明细的期。空店铺清单直接返回 False，不投递（不再表示全部店）。"""
    stores = sorted({store for store in store_ids if store})
    if not stores:
        log.warning("order review recalc skipped: empty store scope (%s)", reason or "-")
        return False
    try:
        with get_session_factory()() as session:
            pairs = periods_for_recalc(session, source_account_ref=SOURCE_REF, store_ids=stores)
            count, _kicked = enqueue_affected(session, pairs, reason=reason)
            return count > 0
    except Exception:
        log.warning("order review recalc enqueue failed (%s)", reason or "-")
        return False


def drain_queue(
    session: Session, *, reason: str, max_items: int = MAX_ITEMS_PER_DRAIN
) -> DrainResult:
    """扫队列；扫完仍有可取的行（到上限，或算的时候又进来）就再踢一次自己。"""
    calculator = OrderReviewCalculator(session, source_account_ref=SOURCE_REF)
    result = drain(
        session,
        source_account_ref=SOURCE_REF,
        recalc=calculator.recalc_period,
        max_items=max_items,
    )
    if result.hit_limit or has_pending(session, source_account_ref=SOURCE_REF):
        session.rollback()
        kick_order_review_recalc(reason="drain_continue")
    log.info(
        "order review recalc (%s): calculated=%s requeued=%s failed=%s lost=%s hit_limit=%s",
        reason or "-",
        result.calculated,
        result.requeued,
        result.failed,
        result.lost,
        result.hit_limit,
    )
    return result


@celery_app.task(name=TASK_NAME, ignore_result=True)  # type: ignore[misc]
def order_review_recalc_task(reason: str = "", store_ids: list[str] | None = None) -> None:
    """扫空重算队列。store_ids 只为兼容升级前已在消息队列里的旧消息：有店铺就先入队，空的忽略。"""
    with get_session_factory()() as session:
        stores = sorted({store for store in store_ids or [] if store})
        if stores:
            pairs = periods_for_recalc(session, source_account_ref=SOURCE_REF, store_ids=stores)
            enqueue(session, source_account_ref=SOURCE_REF, pairs=pairs, reason=reason)
            session.commit()
        drain_queue(session, reason=reason)


@celery_app.task(name=SWEEP_TASK_NAME, ignore_result=True)  # type: ignore[misc]
def order_review_recalc_sweep() -> None:
    """Beat 每 10 分钟：队列里有可取的行才扫（投递失败的兜底）；空队列只花一条 SELECT。"""
    with get_session_factory()() as session:
        if not has_pending(session, source_account_ref=SOURCE_REF):
            return
        session.rollback()
        drain_queue(session, reason="sweep")
