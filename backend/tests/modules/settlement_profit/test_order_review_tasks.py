"""订单审核重算任务：投递参数与失败不抛出。不连 broker。"""

from __future__ import annotations

from typing import Any

import pytest

from app.celery_app import INTEGRATION_QUEUE
from app.modules.settlement_profit import tasks


def test_dispatch_sends_sorted_unique_store_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def apply_async(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(tasks.order_review_recalc_task, "apply_async", apply_async)
    assert (
        tasks.dispatch_order_review_recalc(["b", "a", "", "a"], reason="walmart_bill_sync") is True
    )
    assert calls == [
        {
            "kwargs": {"store_ids": ["a", "b"], "reason": "walmart_bill_sync"},
            "queue": INTEGRATION_QUEUE,
            "routing_key": INTEGRATION_QUEUE,
        }
    ]


def test_dispatch_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: Any) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.order_review_recalc_task, "apply_async", boom)
    assert tasks.dispatch_order_review_recalc(reason="x") is False
    assert tasks.TASK_NAME == "settlement_profit.order_review_recalc"


@pytest.mark.parametrize(
    ("status", "written", "require_success", "due"),
    [
        ("succeeded", 5, True, True),
        ("failed", 5, True, False),  # 成本计价流水失败批次不生效
        ("succeeded", 0, True, False),
        ("failed", 5, False, True),  # 发货单部分店失败，成功店已落库
        ("succeeded", 0, False, False),
    ],
)
def test_order_review_recalc_due(
    status: str, written: int, require_success: bool, due: bool
) -> None:
    from types import SimpleNamespace

    from app.modules.integration_sync.execution import order_review_recalc_due

    result = SimpleNamespace(status=status, records_written=written)
    assert order_review_recalc_due(result, require_success=require_success) is due
    assert order_review_recalc_due(None, require_success=False) is False
