"""订单审核重算的投递：空范围不投递、账单同步按店铺入队、踢任务失败不抛出。不连 broker、不连库。"""

from __future__ import annotations

from typing import Any

import pytest

from app.celery_app import INTEGRATION_QUEUE
from app.modules.settlement_profit import tasks


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def test_empty_store_scope_never_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("empty scope must not reach the queue or the broker")

    monkeypatch.setattr(tasks, "get_session_factory", forbidden)
    monkeypatch.setattr(tasks.order_review_recalc_task, "apply_async", forbidden)
    assert tasks.dispatch_order_review_recalc((), reason="walmart_bill_sync") is False
    assert tasks.dispatch_order_review_recalc(["", ""], reason="walmart_bill_sync") is False


def test_bill_sync_enqueues_periods_of_synced_stores_then_kicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    seen: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def periods(_session: Any, *, source_account_ref: str, store_ids: list[str]) -> Any:
        seen["stores"] = store_ids
        return [("a", "2026-11-03"), ("b", "2026-11-03")]

    def enqueue(_session: Any, *, source_account_ref: str, pairs: Any, reason: str) -> int:
        seen["pairs"] = list(pairs)
        seen["reason"] = reason
        return 2

    monkeypatch.setattr(tasks, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tasks, "periods_for_recalc", periods)
    monkeypatch.setattr(tasks, "enqueue", enqueue)
    monkeypatch.setattr(
        tasks.order_review_recalc_task, "apply_async", lambda **kw: calls.append(kw)
    )
    assert tasks.dispatch_order_review_recalc(["b", "a", "", "a"], reason="walmart_bill_sync")
    assert seen == {
        "stores": ["a", "b"],
        "pairs": [("a", "2026-11-03"), ("b", "2026-11-03")],
        "reason": "walmart_bill_sync",
    }
    assert session.commits == 1
    assert calls == [
        {
            "kwargs": {"reason": "walmart_bill_sync"},
            "queue": INTEGRATION_QUEUE,
            "routing_key": INTEGRATION_QUEUE,
        }
    ]


def test_enqueue_affected_with_no_periods_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()

    def forbidden(**kwargs: Any) -> None:
        raise AssertionError("nothing to recalc, nothing to kick")

    monkeypatch.setattr(tasks.order_review_recalc_task, "apply_async", forbidden)
    count = tasks.enqueue_affected(session, [], reason="x")  # type: ignore[arg-type]
    assert count == 0
    assert session.commits == 0


def test_kick_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: Any) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.order_review_recalc_task, "apply_async", boom)
    assert tasks.kick_order_review_recalc(reason="x") is False
    assert tasks.TASK_NAME == "settlement_profit.order_review_recalc"
