from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.modules.integration_sync.data_pages_mart_invariants import DataPagesMartInvariantError
from app.modules.integration_sync.data_pages_real_sync import DataPagesRealSyncError
from app.modules.integration_sync.execution import SyncRunExecutionService


def _refund_runner(*, provider_denied: bool = False) -> MagicMock:
    runner = MagicMock()
    runner.business_date = date(2026, 10, 26)
    runner.page_size = 100
    runner.heartbeat = None
    runner._fetch_offset_all.return_value = [{"store_id": "store-test"}]
    runner._write_stores.return_value = 1
    runner._fetch_return_all.return_value = [{"return": "synthetic"}]
    runner._write_refunds.return_value = 1
    runner._resolve_refund_items.return_value = 0
    runner._reprice_refunds.return_value = 0
    runner._refund_affected_business_dates = (date(2026, 8, 4),)
    runner.summary = SimpleNamespace(
        return_permission_403=provider_denied,
        store_rows=0,
        refund_rows=0,
        refund_unresolved_rows=0,
        mart_daily_sales_rows=0,
        mart_order_profit_rows=0,
    )
    return runner


def test_refund_facts_commit_before_mart_failure() -> None:
    service = SyncRunExecutionService(MagicMock())
    service._event = MagicMock()
    runner = _refund_runner()
    runner._refresh_daily_sales_mart.side_effect = DataPagesMartInvariantError(
        "DATA_PAGES_SEM_SPEND_UNATTRIBUTED",
        business_date=date(2026, 8, 4),
    )
    run_id = uuid4()

    with pytest.raises(DataPagesMartInvariantError):
        service._execute_data_pages_interface("walmartReturnOrderList", runner, run_id=run_id)

    runner._write_refunds.assert_called_once()
    runner._reprice_refunds.assert_called_once()
    service.session.commit.assert_called_once()
    assert service._event.call_args_list == [
        call(
            run_id,
            "running",
            "running",
            "SYNC_REFUND_FACTS_COMMITTED",
            safe_details={
                "business_date": "2026-10-26",
                "refund_rows": 1,
                "refund_unresolved_rows": 0,
                "affected_purchase_days": 1,
                "purchase_dates": ["2026-08-04"],
            },
        ),
        call(
            run_id,
            "running",
            "running",
            "SYNC_REFUND_MART_PENDING",
            safe_details={"business_date": "2026-08-04"},
        ),
        call(
            run_id,
            "running",
            "running",
            "SYNC_REFUND_MART_PENDING",
            safe_details={"business_date": "2026-10-26"},
        ),
    ]


def test_refund_provider_permission_denied_does_not_commit() -> None:
    service = SyncRunExecutionService(MagicMock())
    service._event = MagicMock()
    runner = _refund_runner(provider_denied=True)

    with pytest.raises(DataPagesRealSyncError, match="DATA_PAGES_REFUND_PERMISSION_DENIED"):
        service._execute_data_pages_interface("walmartReturnOrderList", runner, run_id=uuid4())

    runner._write_refunds.assert_not_called()
    service._event.assert_not_called()
    service.session.commit.assert_not_called()


def test_refund_mart_success_writes_validated_events_after_pending() -> None:
    service = SyncRunExecutionService(MagicMock())
    service._event = MagicMock()
    runner = _refund_runner()
    run_id = uuid4()

    service._execute_data_pages_interface("walmartReturnOrderList", runner, run_id=run_id)

    assert service.session.commit.call_count == 2
    assert [item.args[3] for item in service._event.call_args_list] == [
        "SYNC_REFUND_FACTS_COMMITTED",
        "SYNC_REFUND_MART_PENDING",
        "SYNC_REFUND_MART_PENDING",
        "SYNC_REFUND_MART_VALIDATED",
        "SYNC_REFUND_MART_VALIDATED",
    ]


def test_legacy_refund_retry_reuses_captured_days_not_current_window() -> None:
    service = SyncRunExecutionService(MagicMock())
    source_run_id = uuid4()
    service.repository.refund_capture_business_dates.return_value = (
        date(2026, 8, 4),
        date(2026, 9, 13),
    )
    run = SimpleNamespace(
        interface_key="walmartReturnOrderList",
        retry_of_run_id=source_run_id,
        source_account_ref="synthetic-account",
        window_start=None,
        window_end=None,
    )
    assert service._data_pages_business_dates_for_run(run) == (
        date(2026, 8, 4),
        date(2026, 9, 13),
    )
    service.repository.refund_capture_business_dates.assert_called_once_with(
        source_run_id, "synthetic-account"
    )


def test_legacy_refund_retry_without_capture_evidence_fails_closed() -> None:
    service = SyncRunExecutionService(MagicMock())
    service.repository.refund_capture_business_dates.return_value = ()
    run = SimpleNamespace(
        interface_key="walmartReturnOrderList",
        retry_of_run_id=uuid4(),
        source_account_ref="synthetic-account",
        window_start=None,
        window_end=None,
    )
    assert service._data_pages_business_dates_for_run(run) == ()


def test_refund_retry_with_frozen_window_preserves_original_business_date() -> None:
    service = SyncRunExecutionService(MagicMock())
    la = ZoneInfo("America/Los_Angeles")
    run = SimpleNamespace(
        interface_key="walmartReturnOrderList",
        retry_of_run_id=uuid4(),
        source_account_ref="synthetic-account",
        window_start=datetime(2026, 8, 4, 0, 0, tzinfo=la),
        window_end=datetime(2026, 8, 4, 23, 59, tzinfo=la),
    )
    assert service._data_pages_business_dates_for_run(run) == (date(2026, 8, 4),)
    service.repository.refund_capture_business_dates.assert_not_called()
