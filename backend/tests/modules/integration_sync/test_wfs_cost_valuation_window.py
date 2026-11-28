"""#369 WFS 成本计价流水：定时 / 手动同步的滚动窗口，以及任务中心手动同步放行。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.integrations.lingxing.wfs_cost_valuation_contracts import (
    validate_wfs_cost_valuation_window,
)
from app.modules.integration_sync import service as service_module
from app.modules.integration_sync.fin_shipping_catalog import FIN_SHIPPING_SYNC_SPECS
from app.modules.integration_sync.scheduler import IntegrationSchedulerService
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.wfs_cost_valuation_catalog import WFS_COST_VALUATION_SYNC_SPEC
from app.modules.integration_sync.wfs_cost_valuation_window import (
    WFS_COST_VALUATION_INTERFACE_KEY,
    WFS_COST_VALUATION_ROLLING_DAYS,
    wfs_cost_valuation_rolling_window,
)

ID = UUID("00000000-0000-0000-0000-000000000369")
# UTC 11-27 16:30 = 上海 11-28 00:30：窗口按上海日期算
NOW = datetime(2026, 11, 27, 16, 30, tzinfo=UTC)
EXPECTED = (datetime(2026, 9, 30, tzinfo=UTC), datetime(2026, 11, 28, tzinfo=UTC))


def test_interface_key_matches_catalog() -> None:
    assert WFS_COST_VALUATION_INTERFACE_KEY == WFS_COST_VALUATION_SYNC_SPEC.interface_key


def test_rolling_window_is_last_60_shanghai_days_at_utc_midnight() -> None:
    start, end = wfs_cost_valuation_rolling_window(NOW)
    assert (start, end) == EXPECTED
    assert (end.date() - start.date()).days + 1 == WFS_COST_VALUATION_ROLLING_DAYS == 60
    validate_wfs_cost_valuation_window(start.date(), end.date())  # 在单次 92 天上限内
    with pytest.raises(ValueError):
        wfs_cost_valuation_rolling_window(datetime(2026, 11, 27, 16, 30))


def _due_config() -> SimpleNamespace:
    return SimpleNamespace(
        id=ID,
        interface_id=ID,
        source_account_ref="primary",
        next_run_at=datetime(2026, 11, 27, 16, 0, tzinfo=UTC),
        schedule_cron="0 19 * * *",
        schedule_timezone="UTC",
        max_pages=1000,
        last_scheduled_at=None,
    )


def test_scheduled_run_gets_rolling_window() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    scheduler.repository = MagicMock()
    scheduler.repository.list_due_configs.return_value = [_due_config()]
    scheduler.repository.get_interface.return_value = SimpleNamespace(
        id=ID,
        provider="lingxing",
        interface_key=WFS_COST_VALUATION_INTERFACE_KEY,
        outbound_enabled=True,
    )
    scheduler.repository.find_run_by_idempotency.return_value = None

    scheduler.create_due_runs(now=NOW)

    run = scheduler.repository.add_run.call_args.args[0]
    assert (run.window_start, run.window_end) == EXPECTED
    assert run.trigger_type == "schedule"


def test_other_scheduled_interfaces_keep_no_window() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    scheduler.repository = MagicMock()
    scheduler.repository.list_due_configs.return_value = [_due_config()]
    scheduler.repository.get_interface.return_value = SimpleNamespace(
        id=ID, provider="lingxing", interface_key="productList", outbound_enabled=True
    )
    scheduler.repository.find_run_by_idempotency.return_value = None

    scheduler.create_due_runs(now=NOW)

    run = scheduler.repository.add_run.call_args.args[0]
    assert (run.window_start, run.window_end) == (None, None)


def _manual(
    monkeypatch: pytest.MonkeyPatch, interface: SimpleNamespace
) -> tuple[IntegrationSyncService, dict[str, Any]]:
    service = IntegrationSyncService(MagicMock(spec=Session))
    service.repository = MagicMock()
    service.repository.get_config.return_value = SimpleNamespace(
        id=ID,
        interface_id=ID,
        source_account_ref="primary",
        is_enabled=True,
        schedule_enabled=False,
        max_pages=1000,
    )
    service.repository.get_interface.return_value = interface
    service.repository.find_run_by_idempotency.return_value = None
    captured: dict[str, Any] = {}

    def persist(run: Any, actor_ref: str, record_event: bool = True) -> str:
        captured["run"] = run
        return "queued"

    monkeypatch.setattr(service, "_persist_queued_run", persist)
    monkeypatch.setattr(service_module, "utc_now", lambda: NOW)
    return service, captured


def _interface(spec: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=ID,
        provider="lingxing",
        interface_key=spec.interface_key,
        method="POST",
        endpoint_path=spec.endpoint_path,
        request_kind=spec.request_kind,
        handler_key=spec.handler_key,
        outbound_enabled=True,
    )


def test_manual_wfs_cost_flow_run_is_allowed_with_frozen_rolling_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, captured = _manual(monkeypatch, _interface(WFS_COST_VALUATION_SYNC_SPEC))
    service.create_manual_run(
        ID,
        TriggerRequest(reason="手动同步"),
        actor_ref="u1",
        request_id="r1",
        account_refs=frozenset({"primary"}),
    )
    run = captured["run"]
    # 入队前定死窗口：处理器缺窗口会直接失败，重试沿用同一个窗口
    assert (run.window_start, run.window_end) == EXPECTED
    assert run.trigger_type == "manual"


@pytest.mark.parametrize("spec", FIN_SHIPPING_SYNC_SPECS, ids=lambda s: s.interface_key)
def test_manual_fin_shipping_runs_are_allowed_without_window(
    monkeypatch: pytest.MonkeyPatch, spec: Any
) -> None:
    service, captured = _manual(monkeypatch, _interface(spec))
    service.create_manual_run(
        ID,
        TriggerRequest(reason="手动同步"),
        actor_ref="u1",
        request_id="r1",
        account_refs=frozenset({"primary"}),
    )
    run = captured["run"]
    # 发货单 / 出库单处理器自己算最近 90 天，不在入队时定窗口
    assert (run.window_start, run.window_end) == (None, None)


def test_manual_run_still_rejects_interfaces_outside_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = SimpleNamespace(
        id=ID,
        provider="lingxing",
        interface_key="someOtherInterface",
        method="POST",
        endpoint_path="/x",
        request_kind="offset_page",
        handler_key="lingxing.other.v1",
        outbound_enabled=True,
    )
    service, _ = _manual(monkeypatch, other)
    with pytest.raises(ApiError) as caught:
        service.create_manual_run(
            ID,
            TriggerRequest(reason="手动同步"),
            actor_ref="u1",
            request_id="r1",
            account_refs=frozenset({"primary"}),
        )
    assert caught.value.code == service_module.SYNC_PRODUCTLIST_ONLY
