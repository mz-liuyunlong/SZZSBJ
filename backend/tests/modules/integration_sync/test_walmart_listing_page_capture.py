"""Synthetic Listing page capture and WFS completion marker regressions."""

from contextlib import nullcontext
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.modules.integration_sync.data_pages_real_sync as real_sync
import app.modules.integration_sync.execution as execution


def _response(
    rows: tuple[dict[str, object], ...],
    *,
    page_no: int,
    captured_at: datetime,
    total: int | None = 3,
) -> real_sync.ProviderResponse:
    return real_sync.ProviderResponse(
        parser_key="walmart_listing_list",
        response_json={"code": 0, "data": {"total": total}},
        rows=rows,
        page_no=page_no,
        page_size=2,
        pulled_at=captured_at,
        provider_code=0,
        response_code=200,
    )


@pytest.mark.parametrize(
    ("total", "expected_complete"),
    [(1, True), (None, False), (2, False)],
)
def test_ad_report_page_total_controls_completion_marker(
    monkeypatch, total: int | None, expected_complete: bool
) -> None:
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=2,
        campaign_type="SP",
        max_advertisers=2,
    )
    row = {"advertiserId": "synthetic-advertiser"}
    response = real_sync.ProviderResponse(
        parser_key="walmart_ad_item_sp_list",
        response_json={"code": 0, "data": {"total": total}},
        rows=(row,),
        page_no=1,
        page_size=2,
        pulled_at=datetime(2026, 1, 16, tzinfo=UTC),
        provider_code=0,
        response_code=200,
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: response)

    assert runner._fetch_ads_all("synthetic-advertiser") == [row]
    assert runner.ad_report_capture_complete is expected_complete


def test_advertiser_list_missing_total_cannot_certify_account_day(monkeypatch) -> None:
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=2,
        campaign_type="SP",
        max_advertisers=2,
    )
    response = real_sync.ProviderResponse(
        parser_key="walmart_advertiser_list",
        response_json={"code": 0, "data": {}},
        rows=({"advertiserId": "synthetic-advertiser"},),
        page_no=1,
        page_size=2,
        pulled_at=datetime(2026, 1, 16, tzinfo=UTC),
        provider_code=0,
        response_code=200,
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: response)

    assert len(runner._fetch_page_all("walmart_advertiser_list", runner._advertiser_body)) == 1
    assert runner.ad_report_capture_complete is False


def test_duplicate_listing_uses_its_own_page_capture_time(monkeypatch) -> None:
    first_at = datetime(2026, 1, 15, 15, 59, tzinfo=UTC)
    stocked_at = datetime(2026, 1, 15, 16, 1, tzinfo=UTC)
    first = {
        "store_id": "synthetic-store",
        "item_id": "synthetic-item",
        "msku": "synthetic-msku",
        "wfs_available_quantity": 0,
    }
    other = {
        "store_id": "synthetic-store",
        "item_id": "synthetic-other",
        "msku": "synthetic-other-msku",
        "wfs_available_quantity": 0,
    }
    stocked = {**first, "wfs_available_quantity": 1}
    responses = iter(
        (
            _response((first, other), page_no=1, captured_at=first_at),
            _response((stocked,), page_no=2, captured_at=stocked_at),
        )
    )
    session = MagicMock()
    runner = real_sync.DataPagesRealSyncRunner(
        session=session,
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=2,
        campaign_type="SP",
        max_advertisers=1,
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: next(responses))
    observations: list[tuple[Decimal | None, datetime]] = []
    monkeypatch.setattr(
        real_sync,
        "observe_first_wfs_stock",
        lambda _session, **kwargs: observations.append(
            (kwargs["wfs_quantity"], kwargs["observed_at_utc"])
        ),
    )

    rows = runner._fetch_offset_all("walmart_listing_list", runner._listing_body)
    assert runner._write_listings(rows) == 3
    assert runner.listing_complete_day is None  # Duplicate stable key cannot certify completeness.
    assert observations == [
        (Decimal("0"), first_at),
        (Decimal("0"), first_at),
        (Decimal("1"), stocked_at),
    ]
    inventory_writes = [
        call.args[1]
        for call in session.execute.call_args_list
        if "insert into fact_walmart_listing_inventory_daily" in str(call.args[0])
    ]
    assert inventory_writes == []  # Incomplete retry cannot overwrite certified daily facts.


def test_listing_capture_crossing_la_midnight_keeps_fact_days_separate(monkeypatch) -> None:
    before = datetime(2026, 1, 16, 7, 59, tzinfo=UTC)
    after = datetime(2026, 1, 16, 8, 1, tzinfo=UTC)
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=1,
        campaign_type="SP",
        max_advertisers=1,
    )
    responses = iter(
        (
            _response(({"store_id": "s", "item_id": "a"},), page_no=1, captured_at=before, total=2),
            _response(({"store_id": "s", "item_id": "b"},), page_no=2, captured_at=after, total=2),
        )
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(real_sync, "observe_first_wfs_stock", lambda *_args, **_kwargs: None)

    rows = runner._fetch_offset_all("walmart_listing_list", runner._listing_body)
    runner._write_listings(rows)

    assert runner.listing_complete_day is None
    inventory_writes = [
        call.args[1]
        for call in runner.session.execute.call_args_list
        if "insert into fact_walmart_listing_inventory_daily" in str(call.args[0])
    ]
    assert inventory_writes == []


@pytest.mark.parametrize(
    ("total", "rows", "complete"),
    [
        (2, ({"store_id": "s", "item_id": "a"}, {"store_id": "s", "item_id": "b"}), True),
        (3, ({"store_id": "s", "item_id": "a"}, {"store_id": "s", "item_id": "b"}), False),
        (None, ({"store_id": "s", "item_id": "a"}, {"store_id": "s", "item_id": "b"}), False),
        (0, (), False),
        (2, ({"store_id": "s", "item_id": "a"}, {"store_id": "s", "item_id": "a"}), False),
        (2, ({"store_id": "s", "item_id": "a"}, {"store_id": "s"}), False),
    ],
)
def test_listing_completion_requires_exact_unique_valid_page_total(
    monkeypatch, total: int | None, rows: tuple[dict[str, object], ...], complete: bool
) -> None:
    captured_at = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=2,
        campaign_type="SP",
        max_advertisers=1,
    )
    responses = iter(
        (
            _response(rows, page_no=1, captured_at=captured_at, total=total),
            _response((), page_no=2, captured_at=captured_at, total=total),
        )
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: next(responses))

    runner._fetch_offset_all("walmart_listing_list", runner._listing_body)

    assert (runner.listing_complete_day == date(2026, 1, 15)) is complete


def test_listing_completion_rejects_changing_provider_total(monkeypatch) -> None:
    captured_at = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=1,
        campaign_type="SP",
        max_advertisers=1,
    )
    responses = iter(
        (
            _response(
                ({"store_id": "s", "item_id": "a"},), page_no=1, captured_at=captured_at, total=3
            ),
            _response(
                ({"store_id": "s", "item_id": "b"},), page_no=2, captured_at=captured_at, total=2
            ),
        )
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: next(responses))

    runner._fetch_offset_all("walmart_listing_list", runner._listing_body)

    assert runner.listing_complete_day is None


def test_listing_completion_accepts_two_same_day_pages_with_exact_total(monkeypatch) -> None:
    captured_at = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
    runner = real_sync.DataPagesRealSyncRunner(
        session=MagicMock(),
        client=MagicMock(),
        source_account_ref="synthetic-account",
        business_date=date(2026, 1, 15),
        page_size=2,
        campaign_type="SP",
        max_advertisers=1,
    )
    responses = iter(
        (
            _response(
                ({"store_id": "s", "item_id": "a"}, {"store_id": "s", "item_id": "b"}),
                page_no=1,
                captured_at=captured_at,
            ),
            _response(({"store_id": "s", "item_id": "c"},), page_no=2, captured_at=captured_at),
        )
    )
    monkeypatch.setattr(runner, "_request_page", lambda *_args, **_kwargs: next(responses))

    rows = runner._fetch_offset_all("walmart_listing_list", runner._listing_body)
    assert len(rows) == 3
    assert runner.listing_complete_day == date(2026, 1, 15)
    assert runner.listing_page_count == 2
    runner._write_listings(rows)
    inventory_writes = [
        call.args[1]
        for call in runner.session.execute.call_args_list
        if "insert into fact_walmart_listing_inventory_daily" in str(call.args[0])
    ]
    assert [row["snapshot_date_la"] for row in inventory_writes] == [date(2026, 1, 15)] * 3


@pytest.mark.parametrize(
    "complete,skipped,expected_marker", [(True, 0, True), (False, 0, False), (True, 1, False)]
)
def test_governed_listing_run_emits_marker_only_with_complete_persisted_inventory(
    monkeypatch, complete: bool, skipped: int, expected_marker: bool
) -> None:
    session = MagicMock()
    service = execution.SyncRunExecutionService(session)
    service.repository = MagicMock()
    run = SimpleNamespace(
        id=uuid4(), config_id=None, source_account_ref="synthetic-account", status="running"
    )
    service.repository.get_run_for_update.return_value = run
    service._event = MagicMock()
    event_run_statuses: list[str] = []
    service._event.side_effect = lambda *_args, **_kwargs: event_run_statuses.append(run.status)
    service._heartbeat_data_pages_lock = MagicMock()
    runner = MagicMock()
    runner.session = session
    runner.summary = SimpleNamespace(
        store_rows=0, listing_rows=0, mart_listing_rows=0, listing_skipped_rows=skipped
    )
    runner.listing_complete_day = date(2026, 1, 15) if complete else None
    runner.listing_page_count = 2
    runner._fetch_offset_all.return_value = []
    runner._write_stores.return_value = 0
    runner._write_listings.return_value = 0
    runner._refresh_listing_mart.return_value = 0
    monkeypatch.setattr(execution, "data_pages_client", lambda: nullcontext(MagicMock()))
    monkeypatch.setattr(execution, "DataPagesRealSyncRunner", lambda **_kwargs: runner)
    calls = MagicMock()
    calls.attach_mock(session.commit, "commit")
    calls.attach_mock(service._event, "event")

    service._execute_listing_management_run(run)

    marker_calls = [
        call
        for call in service._event.call_args_list
        if call.args[3] == "SYNC_WFS_INVENTORY_DAY_VALIDATED"
    ]
    assert bool(marker_calls) is expected_marker
    assert event_run_statuses == (["running", "succeeded"] if expected_marker else ["succeeded"])
    if expected_marker:
        assert marker_calls[0].kwargs["safe_details"] == {
            "business_date": "2026-01-15",
            "page_count": 2,
            "row_count": 0,
        }
        assert [call[0] for call in calls.mock_calls] == [
            "commit",
            "event",
            "event",
            "commit",
        ]


def test_governed_listing_run_does_not_commit_marker_when_mart_refresh_fails(
    monkeypatch,
) -> None:
    session = MagicMock()
    service = execution.SyncRunExecutionService(session)
    service.repository = MagicMock()
    service._event = MagicMock()
    service._heartbeat_data_pages_lock = MagicMock()
    runner = MagicMock()
    runner.session = session
    runner.summary = SimpleNamespace(
        store_rows=1, listing_rows=1, mart_listing_rows=0, listing_skipped_rows=0
    )
    runner.listing_complete_day = date(2026, 1, 15)
    runner._fetch_offset_all.return_value = []
    runner._refresh_listing_mart.side_effect = RuntimeError("synthetic mart failure")
    monkeypatch.setattr(execution, "data_pages_client", lambda: nullcontext(MagicMock()))
    monkeypatch.setattr(execution, "DataPagesRealSyncRunner", lambda **_kwargs: runner)
    run = SimpleNamespace(id=uuid4(), config_id=None, source_account_ref="synthetic-account")

    with pytest.raises(RuntimeError, match="synthetic mart failure"):
        service._execute_listing_management_run(run)

    assert session.commit.call_count == 1  # Only the initial run metadata was committed.
    service._event.assert_not_called()


@pytest.mark.parametrize(
    ("final_status", "error_code"),
    [(None, "SYNC_RUN_NOT_FOUND"), ("failed", "SYNC_RUN_NOT_RUNNING")],
)
def test_governed_listing_run_does_not_commit_inventory_if_run_cannot_be_finalized(
    monkeypatch,
    final_status: str | None,
    error_code: str,
) -> None:
    session = MagicMock()
    service = execution.SyncRunExecutionService(session)
    service.repository = MagicMock()
    service.repository.get_run_for_update.return_value = (
        None if final_status is None else SimpleNamespace(status=final_status)
    )
    service._event = MagicMock()
    service._heartbeat_data_pages_lock = MagicMock()
    runner = MagicMock()
    runner.session = session
    runner.summary = SimpleNamespace(
        store_rows=1, listing_rows=1, mart_listing_rows=1, listing_skipped_rows=0
    )
    runner.listing_complete_day = date(2026, 1, 15)
    runner._fetch_offset_all.return_value = []
    monkeypatch.setattr(execution, "data_pages_client", lambda: nullcontext(MagicMock()))
    monkeypatch.setattr(execution, "DataPagesRealSyncRunner", lambda **_kwargs: runner)
    run = SimpleNamespace(id=uuid4(), config_id=None, source_account_ref="synthetic-account")

    with pytest.raises(real_sync.DataPagesRealSyncError, match=error_code):
        service._execute_listing_management_run(run)

    assert session.commit.call_count == 1  # The inventory transaction was not committed.
    service._event.assert_not_called()
