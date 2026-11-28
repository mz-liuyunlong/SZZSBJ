"""订单审核重算队列（settlement_recalc_queue，迁移 0105）。

投递去重、同一期串行、算的时候进来的新数据不漏：

- enqueue：按 (账号, 店铺, 账期) upsert；已在队列里只 generation + 1、requested_count + 1、
  更新 requested_at 和 reason，不新增行；done / failed 的行回到 queued；running 的行保持 running。
- drain：一行一行取（FOR UPDATE SKIP LOCKED），置 running 并记下取走时的 generation，提交后再算；
  算完比 generation：变了回到 queued 再算，没变置 done；出错置 failed（下次投递会回到 queued）。
  running 超过租约（worker 中途退出）视为可重取。期本身的串行仍靠 recalc_period 里的期账单行锁。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.settlement_profit.models import SettlementRecalcQueue

log = logging.getLogger(__name__)

RUNNING_LEASE = timedelta(minutes=30)
MAX_ITEMS_PER_DRAIN = 5000


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Claim:
    queue_id: object
    store_id: str
    period_key: str
    generation: int


@dataclass(slots=True)
class DrainResult:
    calculated: int = 0
    requeued: int = 0
    failed: int = 0


def enqueue(
    session: Session,
    *,
    source_account_ref: str,
    pairs: Iterable[tuple[str, str]],
    reason: str,
    now: datetime | None = None,
) -> int:
    """把 (店铺, 账期) 放进队列；返回涉及的期数。不提交，由调用方提交。"""
    unique = sorted({(store, period) for store, period in pairs if store and period})
    if not unique:
        return 0
    at = now or utc_now()
    queue = SettlementRecalcQueue
    statement = pg_insert(queue).values(
        [
            {
                "source_account_ref": source_account_ref,
                "store_id": store,
                "period_key": period,
                "status": "queued",
                "generation": 1,
                "requested_count": 1,
                "reason": reason[:128] or None,
                "requested_at": at,
                "updated_at": at,
            }
            for store, period in unique
        ]
    )
    excluded = statement.excluded
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["source_account_ref", "store_id", "period_key"],
            set_={
                "generation": queue.generation + 1,
                "requested_count": queue.requested_count + 1,
                "requested_at": excluded.requested_at,
                "reason": excluded.reason,
                "updated_at": excluded.updated_at,
                "status": case((queue.status == "running", queue.status), else_="queued"),
            },
        )
    )
    return len(unique)


def claim_next(
    session: Session, *, source_account_ref: str, now: datetime | None = None
) -> Claim | None:
    """取一行置 running 并提交；没有可取的返回 None。"""
    at = now or utc_now()
    queue = SettlementRecalcQueue
    row = session.scalars(
        select(queue)
        .where(
            queue.source_account_ref == source_account_ref,
            or_(
                queue.status == "queued",
                (queue.status == "running") & (queue.started_at < at - RUNNING_LEASE),
            ),
        )
        .order_by(queue.requested_at, queue.store_id, queue.period_key)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if row is None:
        session.rollback()
        return None
    row.status = "running"
    row.claimed_generation = row.generation
    row.started_at = at
    row.updated_at = at
    claim = Claim(row.id, row.store_id, row.period_key, row.generation)
    session.commit()
    return claim


def finish(
    session: Session, claim: Claim, *, error: str | None = None, now: datetime | None = None
) -> bool:
    """算完：期间又被投递过（generation 变了）回到 queued 并返回 True；否则 done / failed。"""
    at = now or utc_now()
    row = session.scalars(
        select(SettlementRecalcQueue)
        .where(SettlementRecalcQueue.id == claim.queue_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        session.commit()
        return False
    requeue = row.generation != claim.generation
    if requeue:
        row.status = "queued"
    elif error is not None:
        row.status = "failed"
    else:
        row.status = "done"
    row.last_error = error
    row.finished_at = at
    row.updated_at = at
    session.commit()
    return requeue


def drain(
    session: Session,
    *,
    source_account_ref: str,
    recalc: Callable[[str, str], object],
    max_items: int = MAX_ITEMS_PER_DRAIN,
) -> DrainResult:
    """一直取到队列空（或到上限）；recalc(store_id, period_key) 由调用方给，算完调用方不提交。"""
    result = DrainResult()
    for _ in range(max_items):
        claim = claim_next(session, source_account_ref=source_account_ref)
        if claim is None:
            break
        error: str | None = None
        try:
            recalc(claim.store_id, claim.period_key)
            session.commit()
            result.calculated += 1
        except Exception as exc:
            session.rollback()
            error = type(exc).__name__[:64]
            result.failed += 1
            log.exception("order review recalc failed for one period (%s)", claim.period_key)
        if finish(session, claim, error=error):
            result.requeued += 1
    return result
