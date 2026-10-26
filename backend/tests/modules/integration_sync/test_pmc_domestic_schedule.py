from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (
    DOMESTIC_SCHEDULE_ZONE,
    LingxingDomesticWarehouseListSyncHandler,
    LingxingDomesticWarehouseStatementSyncHandler,
    PmcDomesticSyncError,
)


def _handler(handler_type):
    handler = handler_type(MagicMock())
    handler.repository = MagicMock()
    handler.repository.get_config.return_value = SimpleNamespace(
        is_enabled=True,
        schedule_enabled=True,
    )
    handler.repository.get_retention_policy.return_value = SimpleNamespace()
    return handler


def _run(interface_key: str, trigger_type: str = "schedule"):
    return SimpleNamespace(
        trigger_type=trigger_type,
        provider="lingxing",
        interface_key=interface_key,
        config_id=uuid4(),
        source_account_ref="primary",
        window_start=None,
        window_end=None,
    )


def _interface(handler) -> SimpleNamespace:
    return SimpleNamespace(handler_key=handler.handler_key, outbound_enabled=True)


def test_scheduled_statement_run_uses_shanghai_ninety_day_window() -> None:
    handler = _handler(LingxingDomesticWarehouseStatementSyncHandler)
    run = _run("domesticWarehouseStatement")

    _config, _policy, window = handler._preflight(run, _interface(handler))

    assert window[0] is not None and window[1] is not None
    assert (window[1] - window[0]).days == 89
    assert run.window_start.tzinfo == DOMESTIC_SCHEDULE_ZONE
    assert run.window_end.tzinfo == DOMESTIC_SCHEDULE_ZONE


def test_scheduled_snapshot_run_does_not_require_a_window() -> None:
    handler = _handler(LingxingDomesticWarehouseListSyncHandler)
    run = _run("domesticWarehouseList")

    _config, _policy, window = handler._preflight(run, _interface(handler))

    assert window == (None, None)
    assert run.window_start is None


def test_manual_statement_run_still_requires_a_window() -> None:
    handler = _handler(LingxingDomesticWarehouseStatementSyncHandler)
    run = _run("domesticWarehouseStatement", "manual")

    with pytest.raises(PmcDomesticSyncError, match="SYNC_DOMESTIC_WINDOW_REQUIRED"):
        handler._preflight(run, _interface(handler))


def test_unscheduled_trigger_stays_unauthorized() -> None:
    handler = _handler(LingxingDomesticWarehouseListSyncHandler)
    run = _run("domesticWarehouseList", "backfill")

    with pytest.raises(PmcDomesticSyncError, match="SYNC_DOMESTIC_EXECUTION_NOT_AUTHORIZED"):
        handler._preflight(run, _interface(handler))
