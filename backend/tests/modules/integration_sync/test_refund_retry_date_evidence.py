"""Refund retry date provenance: no implicit window or widening across retry chains."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.api import ApiError
from app.modules.integration_sync.service import IntegrationSyncService


def _run(*, parent=None, account="account-a", start=None, end=None):
    return SimpleNamespace(
        work_items_total=0,
        id=uuid4(),
        retry_of_run_id=parent,
        source_account_ref=account,
        provider="lingxing",
        interface_key="walmartReturnOrderList",
        window_start=start,
        window_end=end,
        work_items_total=0,
    )


def test_refund_retry_recovers_exact_ancestor_window() -> None:
    session = MagicMock()
    service = IntegrationSyncService(session)
    original = _run(
        start=datetime(2026, 10, 20, tzinfo=ZoneInfo("America/Los_Angeles")),
        end=datetime(2026, 10, 22, 23, 59, tzinfo=ZoneInfo("America/Los_Angeles")),
    )
    parent = _run(parent=original.id)
    source = _run(parent=parent.id)
    service.repository = MagicMock()
    service.repository.get_run.side_effect = lambda uid, scope: {
        parent.id: parent,
        original.id: original,
    }.get(uid)
    service.repository.refund_capture_business_dates.return_value = ()
    assert service._refund_retry_window(source, frozenset({"account-a"})) == (
        original.window_start,
        original.window_end,
    )


def test_refund_retry_rejects_missing_evidence_without_queuing() -> None:
    service = IntegrationSyncService(MagicMock())
    source = _run()
    service.repository = MagicMock()
    service.repository.refund_capture_business_dates.return_value = ()
    with pytest.raises(ApiError):
        service._refund_retry_window(source, frozenset({"account-a"}))
    service.repository.add_run.assert_not_called()


def test_refund_retry_rejects_cross_account_ancestor() -> None:
    service = IntegrationSyncService(MagicMock())
    other = _run(account="account-b")
    source = _run(parent=other.id)
    service.repository = MagicMock()
    service.repository.get_run.return_value = other
    service.repository.refund_capture_business_dates.return_value = ()
    with pytest.raises(ApiError):
        service._refund_retry_window(source, frozenset({"account-a"}))


def test_refund_retry_rejects_sparse_evidence() -> None:
    service = IntegrationSyncService(MagicMock())
    source = _run()
    service.repository = MagicMock()
    service.repository.refund_capture_business_dates.return_value = (
        date(2026, 10, 20),
        date(2026, 10, 22),
    )
    with pytest.raises(ApiError):
        service._refund_retry_window(source, frozenset({"account-a"}))


def test_refund_retry_accepts_contiguous_capture_evidence() -> None:
    service = IntegrationSyncService(MagicMock())
    source = _run()
    service.repository = MagicMock()
    source.work_items_total = 2
    service.repository.refund_capture_business_dates.return_value = (
        date(2026, 10, 20),
        date(2026, 10, 21),
    )
    start, end = service._refund_retry_window(source, frozenset({"account-a"}))
    assert start.date() == date(2026, 10, 20)
    assert end.date() == date(2026, 10, 21)
    assert start.tzinfo is not None and end.tzinfo is not None


def test_refund_retry_rejects_cycle() -> None:
    service = IntegrationSyncService(MagicMock())
    source = _run()
    source.retry_of_run_id = source.id
    service.repository = MagicMock()
    service.repository.refund_capture_business_dates.return_value = ()
    service.repository.get_run.return_value = source
    with pytest.raises(ApiError):
        service._refund_retry_window(source, frozenset({"account-a"}))
