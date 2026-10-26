from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.modules.warehouse_wfs.anomaly_detection import WfsSalesEvidence
from app.modules.warehouse_wfs.sales_reader import (
    WfsSalesReadError,
    read_walmart_lifetime_sales,
)


def session_with(
    *,
    listing_count: int,
    aggregate: tuple[object, ...],
    listing_start_at: datetime | None = None,
    sync_windows: list[tuple[datetime, datetime]] | None = None,
) -> MagicMock:
    session = MagicMock()
    listing_result = MagicMock()
    listing_result.all.return_value = [
        ("primary", "store-a", "item-a", "SKU-A", listing_start_at)
    ] * listing_count
    aggregate_result = MagicMock()
    aggregate_result.all.return_value = (
        [("primary", "store-a", "item-a", "SKU-A", *aggregate)] if aggregate[3] else []
    )
    windows_result = MagicMock()
    windows_result.all.return_value = [
        ("primary", start, end, {"store_id": "store-a"}) for start, end in sync_windows or []
    ]
    session.execute.side_effect = [listing_result, aggregate_result, windows_result]
    return session


def read(session: MagicMock) -> WfsSalesEvidence:
    return read_walmart_lifetime_sales(
        session,
        source_account_ref="primary",
        store_id="store-a",
        item_id="item-a",
        msku="SKU-A",
    )


def test_rows_without_lifecycle_watermark_are_unknown_not_complete() -> None:
    result = read(
        session_with(
            listing_count=1,
            aggregate=(Decimal("87"), date(2026, 7, 3), date(2026, 9, 22), 31),
        )
    )
    assert result.historical_units == Decimal("87")
    assert result.sales_start_date == date(2026, 7, 3)
    assert result.sales_end_date == date(2026, 9, 22)
    assert result.coverage_status == "unknown"
    assert result.coverage_reason == "product_lifecycle_start_unproven"


def test_missing_rows_are_unknown_not_zero() -> None:
    result = read(session_with(listing_count=1, aggregate=(None, None, None, 0)))
    assert result.historical_units is None
    assert result.coverage_status == "missing"


@pytest.mark.parametrize("listing_count", [0, 2])
def test_ambiguous_listing_is_rejected(listing_count: int) -> None:
    with pytest.raises(WfsSalesReadError, match="IDENTITY_UNRESOLVED"):
        read(session_with(listing_count=listing_count, aggregate=(None, None, None, 0)))


def test_fractional_or_negative_sales_are_rejected() -> None:
    with pytest.raises(WfsSalesReadError, match="INVALID_LIFETIME_SALES"):
        read(
            session_with(
                listing_count=1,
                aggregate=(Decimal("1.5"), date(2026, 1, 1), date(2026, 1, 1), 1),
            )
        )


def test_verified_contiguous_sync_windows_prove_complete_lifecycle_coverage() -> None:
    session = session_with(
        listing_count=1,
        listing_start_at=datetime(2026, 7, 3, 7, tzinfo=UTC),
        aggregate=(Decimal("87"), date(2026, 7, 3), date(2026, 9, 22), 31),
        sync_windows=[
            (
                datetime(2026, 7, 3, tzinfo=UTC),
                datetime(2026, 8, 31, tzinfo=UTC),
            ),
            (
                datetime(2026, 9, 1, tzinfo=UTC),
                datetime(2026, 10, 17, tzinfo=UTC),
            ),
        ],
    )

    result = read_walmart_lifetime_sales(
        session,
        source_account_ref="primary",
        store_id="store-a",
        item_id="item-a",
        msku="SKU-A",
        required_coverage_end=date(2026, 10, 17),
    )

    assert result.coverage_status == "complete"
    assert result.coverage_start_date == date(2026, 7, 3)
    assert result.coverage_end_date == date(2026, 10, 17)
    assert result.coverage_reason == "verified_contiguous_sync_windows"
    assert result.source_watermark == "saleStatPageList:2026-07-03:2026-10-17"


def test_sync_window_gap_is_partial_not_complete() -> None:
    session = session_with(
        listing_count=1,
        listing_start_at=datetime(2026, 7, 3, 7, tzinfo=UTC),
        aggregate=(Decimal("87"), date(2026, 7, 3), date(2026, 9, 22), 31),
        sync_windows=[
            (
                datetime(2026, 7, 3, tzinfo=UTC),
                datetime(2026, 8, 31, tzinfo=UTC),
            ),
            (
                datetime(2026, 9, 2, tzinfo=UTC),
                datetime(2026, 10, 17, tzinfo=UTC),
            ),
        ],
    )

    result = read_walmart_lifetime_sales(
        session,
        source_account_ref="primary",
        store_id="store-a",
        item_id="item-a",
        msku="SKU-A",
        required_coverage_end=date(2026, 10, 17),
    )

    assert result.coverage_status == "partial"
    assert result.coverage_reason == "sync_window_gap"
