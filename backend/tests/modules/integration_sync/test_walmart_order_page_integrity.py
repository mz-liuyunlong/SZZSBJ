"""Synthetic, transport-free order pagination and LA date-boundary regressions."""

from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncError,
    DataPagesRealSyncRunner,
    ProviderResponse,
    _la_day_epoch,
    _order_purchase_date_la,
)


class _OrderClient:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, parser_key: str, body: dict[str, Any], **_kwargs: Any) -> ProviderResponse:
        self.calls.append((parser_key, body))
        return self.responses.pop(0)


def _page(*, count: int, total: int | None) -> ProviderResponse:
    rows = tuple({"global_order_no": f"synthetic-order-{i}"} for i in range(count))
    data: dict[str, Any] = {"list": list(rows)}
    if total is not None:
        data["total"] = total
    return ProviderResponse(
        parser_key="order_v2_list",
        response_json={"code": 0, "data": data},
        rows=rows,
        page_no=1,
        page_size=2,
        pulled_at=datetime.now(UTC),
        provider_code=0,
        response_code=200,
    )


def _runner(client: _OrderClient) -> DataPagesRealSyncRunner:
    runner = DataPagesRealSyncRunner(
        session=cast(Session, object()),
        client=cast(Any, client),
        source_account_ref="synthetic",
        business_date=date(2026, 10, 16),
        page_size=2,
        campaign_type="SP",
        max_advertisers=1,
    )
    runner.store_ids = ("synthetic-store",)
    runner._persist_raw_blob = cast(Any, lambda *_args, **_kwargs: None)
    return runner


def test_order_pagination_fails_closed_when_provider_total_exceeds_short_last_page() -> None:
    client = _OrderClient([_page(count=2, total=4), _page(count=1, total=4)])
    runner = _runner(client)

    with pytest.raises(DataPagesRealSyncError, match="DATA_PAGES_ORDER_PAGINATION_INCOMPLETE"):
        runner._fetch_offset_all("order_v2_list", runner._order_body)

    assert len(client.calls) == 2
    assert client.calls[0][1]["offset"] == 0
    assert client.calls[1][1]["offset"] == 2


def test_order_pagination_fails_closed_on_empty_page_with_remaining_total() -> None:
    client = _OrderClient([_page(count=0, total=2)])
    runner = _runner(client)

    with pytest.raises(DataPagesRealSyncError, match="DATA_PAGES_ORDER_PAGINATION_INCOMPLETE"):
        runner._fetch_offset_all("order_v2_list", runner._order_body)


def test_order_pagination_accepts_exact_reported_total() -> None:
    client = _OrderClient([_page(count=2, total=3), _page(count=1, total=3)])
    runner = _runner(client)

    assert len(runner._fetch_offset_all("order_v2_list", runner._order_body)) == 3
    assert len(client.calls) == 2


def test_order_pagination_keeps_short_page_contract_when_total_unavailable() -> None:
    client = _OrderClient([_page(count=1, total=None)])
    runner = _runner(client)

    assert len(runner._fetch_offset_all("order_v2_list", runner._order_body)) == 1


def test_la_business_day_has_23_and_25_hours_across_dst_changes() -> None:
    spring = date(2026, 3, 8)
    fall = date(2026, 11, 1)

    assert _la_day_epoch(spring, end=True) - _la_day_epoch(spring, end=False) + 1 == 23 * 3600
    assert _la_day_epoch(fall, end=True) - _la_day_epoch(fall, end=False) + 1 == 25 * 3600


def test_la_purchase_day_matches_second_and_millisecond_epoch_boundaries() -> None:
    day_start = _la_day_epoch(date(2026, 10, 16), end=False)
    previous_day_end = day_start - 1

    assert _order_purchase_date_la(str(previous_day_end)) == date(2026, 10, 15)
    assert _order_purchase_date_la(str(day_start)) == date(2026, 10, 16)
    assert _order_purchase_date_la(str(day_start * 1000)) == date(2026, 10, 16)
