"""Synthetic pagination regression for first WFS-stock observation timing."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import app.modules.integration_sync.data_pages_real_sync as real_sync


def _response(
    rows: tuple[dict[str, object], ...], *, page_no: int, captured_at: datetime
) -> real_sync.ProviderResponse:
    return real_sync.ProviderResponse(
        parser_key="walmart_listing_list",
        response_json={"code": 0, "data": {"total": 3}},
        rows=rows,
        page_no=page_no,
        page_size=2,
        pulled_at=captured_at,
        provider_code=0,
        response_code=200,
    )


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
    assert observations == [
        (Decimal("0"), first_at),
        (Decimal("0"), first_at),
        (Decimal("1"), stocked_at),
    ]
