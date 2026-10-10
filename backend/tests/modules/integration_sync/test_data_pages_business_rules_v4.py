import inspect
from datetime import date
from unittest.mock import MagicMock

import pytest

import app.modules.integration_sync.data_pages_business_rules_v4 as v4_module
from app.modules.integration_sync.data_pages_business_rules_v3 import (
    DataPagesRealSyncRunner as HistoricalAdRunner,
)
from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner


def test_v4_writes_refunds_into_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._write_refunds)

    assert "build_rows" in source
    assert "AfterSalesReasonClassifier" in source
    assert "delete_excluded_rows" in source
    assert "upsert_rows" in source


def test_v4_collects_refund_purchase_days_only_when_salestat_exists() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._reprice_refunds)

    assert "r.return_order_at::date=:refund_day" in source
    assert "r.purchase_time_at::date" in source
    assert "fact_walmart_sales_item_daily" in source
    assert "s.business_date_la=r.purchase_time_at::date" in source
    assert "s.allocation_status='direct'" in source
    assert "interval '15 hours'" not in source
    assert "dws_walmart_refund_business_amounts" not in source


def test_v4_refreshes_affected_refund_purchase_days() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "_refund_affected_business_dates" in source
    assert "super()._refresh_order_profit_mart()" in source
    assert "validate_automatic_mart_replay" in source


def test_v4_replays_and_validates_current_and_refund_purchase_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_day = date(2026, 1, 15)
    refund_purchase_day = date(2026, 1, 10)
    daily_calls: list[date] = []
    order_calls: list[date] = []
    snapshots: list[tuple[date, int]] = []
    validations: list[tuple[object, object]] = []
    heartbeat = MagicMock()

    def refresh_daily(runner: DataPagesRealSyncRunner) -> int:
        daily_calls.append(runner.business_date)
        return 11 if runner.business_date == current_day else 7

    def refresh_order(runner: DataPagesRealSyncRunner) -> int:
        order_calls.append(runner.business_date)
        return 5 if runner.business_date == current_day else 3

    def snapshot(_session: object, _account: str, day: date) -> tuple[date, int]:
        value = (day, len(snapshots))
        snapshots.append(value)
        return value

    monkeypatch.setattr(HistoricalAdRunner, "_refresh_daily_sales_mart", refresh_daily)
    monkeypatch.setattr(HistoricalAdRunner, "_refresh_order_profit_mart", refresh_order)
    monkeypatch.setattr(v4_module, "snapshot_automatic_marts", snapshot)
    monkeypatch.setattr(
        v4_module,
        "validate_automatic_mart_replay",
        lambda first, replay, **_kwargs: validations.append((first, replay)),
    )

    runner = DataPagesRealSyncRunner(
        session=MagicMock(),
        client=None,
        source_account_ref="synthetic-account",
        business_date=current_day,
        page_size=100,
        campaign_type="SP",
        max_advertisers=1,
        heartbeat=heartbeat,
    )
    runner._refund_affected_business_dates = (refund_purchase_day,)

    assert runner._refresh_daily_sales_mart() == 11
    assert daily_calls == [refund_purchase_day, refund_purchase_day, current_day, current_day]
    assert order_calls == [refund_purchase_day, refund_purchase_day, current_day, current_day]
    assert len(validations) == 2
    assert heartbeat.call_count == 2
    assert runner.business_date == current_day
    assert runner._refresh_order_profit_mart() == 5
    assert order_calls == [refund_purchase_day, refund_purchase_day, current_day, current_day]


def test_v4_refund_identity_health_reads_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._resolve_refund_items)

    assert "after_sales_refund_items" in source
    assert "return_order_at::date=:day" in source
    assert "fact_walmart_refund_items" not in source


def test_refund_empty_list_is_valid_payload() -> None:
    from datetime import date

    from scripts.import_after_sales_refund_items import (
        build_rows,
        collect_excluded_item_keys,
        find_return_list,
        summarize_refund_payload,
    )

    payload = {"data": {"list": []}}

    assert find_return_list(payload) == []
    assert (
        build_rows(
            payload,
            source_account_ref="primary",
            target_date=date(2026, 10, 9),
            listing_map={},
            cost_map={},
        )
        == []
    )
    assert collect_excluded_item_keys(payload) == []
    summary = summarize_refund_payload(payload)
    assert summary["raw_item_rows"] == 0
    assert summary["counted_rows"] == 0
