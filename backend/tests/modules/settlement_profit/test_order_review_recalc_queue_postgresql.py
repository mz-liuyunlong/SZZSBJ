"""订单审核按范围重算 + 重算队列（刘云龙 #377 终审）。合成数据；没配隔离库就跳过。

- affected_periods：只返回当前版本订单行里对得上 (店铺, MSKU) / (店铺, 订单号) 的期。
- 队列：连续投递合并成一次；算的时候又投递会再算一次、不漏；出错置 failed、再投递回到 queued；
  running 超过租约可重取。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.settlement_profit.models import SettlementOrderLine, SettlementRecalcQueue
from app.modules.settlement_profit.order_review import recalc_queue
from app.modules.settlement_profit.order_review.recalc_scope import AffectedKeys, affected_periods

ACCOUNT = "primary"
STORE_A = "990000000000000001"
STORE_B = "990000000000000002"
P1, P2 = "2026-11-03", "2026-11-17"


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    engine.dispose()


def add_line(
    session: Session,
    store: str,
    period: str,
    *,
    msku: str | None,
    order: str = "900000000000000001",
    current: bool = True,
    version: int = 1,
) -> None:
    session.add(
        SettlementOrderLine(
            source_account_ref=ACCOUNT,
            store_id=store,
            period_key=period,
            bill_month=date(2026, 11, 1),
            line_key=f"{store}-{period}-{order}-{msku}-{version}",
            is_current=current,
            line_kind="sale",
            fulfillment_type="wfs",
            platform_order_no=order,
            order_line_no="1",
            msku=msku,
            calc_version=version,
            content_hash="0" * 64,
        )
    )
    session.flush()


Pairs = tuple[tuple[str | None, str], ...]


def keys(*, mskus: Pairs = (), orders: Pairs = ()) -> AffectedKeys:
    out = AffectedKeys()
    for store, msku in mskus:
        out.add(store, mskus=[msku])
    for store, order in orders:
        out.add(store, orders=[order])
    return out


def periods(session: Session, scope: AffectedKeys) -> list[tuple[str, str]]:
    return affected_periods(session, source_account_ref=ACCOUNT, keys=scope)


def test_one_store_write_only_hits_that_store(session: Session) -> None:
    add_line(session, STORE_A, P1, msku="SYN-001")
    add_line(session, STORE_B, P1, msku="SYN-001")
    # 店铺 A 的 MSKU（大小写、空格不同也能对上）只命中店铺 A
    assert periods(session, keys(mskus=((STORE_A, " syn-001 "),))) == [(STORE_A, P1)]
    # 店铺没认出（成本计价流水 unmapped）= 任何店铺
    assert periods(session, keys(mskus=((None, "SYN-001"),))) == [(STORE_A, P1), (STORE_B, P1)]


def test_one_msku_only_hits_periods_that_contain_it(session: Session) -> None:
    add_line(session, STORE_A, P1, msku="SYN-001")
    add_line(session, STORE_A, P2, msku="SYN-002", order="900000000000000002")
    # 旧版本（不是当前）里有这个 MSKU 也不算
    add_line(session, STORE_A, P2, msku="SYN-001", current=False, version=9)
    assert periods(session, keys(mskus=((STORE_A, "SYN-001"),))) == [(STORE_A, P1)]
    assert periods(session, keys(orders=((STORE_A, "900000000000000002"),))) == [(STORE_A, P2)]
    assert periods(session, keys(mskus=((STORE_A, "SYN-404"),))) == []
    assert periods(session, AffectedKeys()) == []


def queue_row(session: Session, store: str = STORE_A, period: str = P1) -> SettlementRecalcQueue:
    session.expire_all()
    return session.scalars(
        select(SettlementRecalcQueue).where(
            SettlementRecalcQueue.store_id == store, SettlementRecalcQueue.period_key == period
        )
    ).one()


def enqueue(session: Session, pairs: list[tuple[str, str]], reason: str = "test") -> None:
    recalc_queue.enqueue(session, source_account_ref=ACCOUNT, pairs=pairs, reason=reason)
    session.commit()


def test_four_syncs_in_a_row_recalc_the_period_once(session: Session) -> None:
    for reason in ("finShippingList_sync", "finShippingDetail_sync", "finWmsOutboundOrders_sync"):
        enqueue(session, [(STORE_A, P1)], reason)
    enqueue(session, [(STORE_A, P1), (STORE_A, P1)], "wfs_cost_flow_sync")
    calls: list[tuple[str, str]] = []
    result = recalc_queue.drain(
        session, source_account_ref=ACCOUNT, recalc=lambda s, p: calls.append((s, p))
    )
    assert calls == [(STORE_A, P1)]
    assert (result.calculated, result.requeued, result.failed) == (1, 0, 0)
    row = queue_row(session)
    assert (row.status, row.requested_count, row.generation) == ("done", 4, 4)
    assert row.reason == "wfs_cost_flow_sync"


def test_new_request_while_running_is_recalculated_again(session: Session) -> None:
    enqueue(session, [(STORE_A, P1)])
    calls: list[str] = []

    def recalc(store: str, period: str) -> None:
        calls.append(period)
        if len(calls) == 1:
            # 算的时候又来了新数据：保持 running，只把 generation + 1
            enqueue(session, [(store, period)], "arrived_while_running")
            assert queue_row(session).status == "running"

    result = recalc_queue.drain(session, source_account_ref=ACCOUNT, recalc=recalc)
    assert calls == [P1, P1]
    assert (result.calculated, result.requeued) == (2, 1)
    assert queue_row(session).status == "done"


def test_failure_marks_failed_and_next_request_queues_again(session: Session) -> None:
    enqueue(session, [(STORE_A, P1)])

    def boom(store: str, period: str) -> None:
        raise RuntimeError("synthetic")

    result = recalc_queue.drain(session, source_account_ref=ACCOUNT, recalc=boom)
    assert result.failed == 1
    row = queue_row(session)
    assert (row.status, row.last_error) == ("failed", "RuntimeError")
    enqueue(session, [(STORE_A, P1)])
    assert queue_row(session).status == "queued"


def test_stale_running_row_can_be_claimed_again(session: Session) -> None:
    enqueue(session, [(STORE_A, P1), (STORE_B, P2)])
    now = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    first = recalc_queue.claim_next(session, source_account_ref=ACCOUNT, now=now)
    assert first is not None
    # 另一行在 running 期间不会被再取到；超过租约才会
    second = recalc_queue.claim_next(session, source_account_ref=ACCOUNT, now=now)
    assert second is not None and second.queue_id != first.queue_id
    assert recalc_queue.claim_next(session, source_account_ref=ACCOUNT, now=now) is None
    later = now + recalc_queue.RUNNING_LEASE + timedelta(minutes=1)
    again = recalc_queue.claim_next(session, source_account_ref=ACCOUNT, now=later)
    assert again is not None and again.queue_id in {first.queue_id, second.queue_id}
