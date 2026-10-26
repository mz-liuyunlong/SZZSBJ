from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.modules.warehouse_wfs.anomaly_detection import WfsSalesEvidence
from app.modules.warehouse_wfs.sales_reader import (
    WfsSalesReadError,
    read_walmart_lifetime_sales,
)


def session_with(*, listing_count: int, aggregate: tuple[object, ...]) -> MagicMock:
    session = MagicMock()
    session.scalar.return_value = listing_count
    session.execute.return_value.one.return_value = aggregate
    return session


def read(session: MagicMock) -> WfsSalesEvidence:
    return read_walmart_lifetime_sales(
        session,
        source_account_ref="primary",
        store_id="store-a",
        item_id="item-a",
        msku="SKU-A",
    )


def test_reads_exact_lifetime_sales_and_coverage() -> None:
    result = read(
        session_with(
            listing_count=1,
            aggregate=(Decimal("87"), date(2026, 7, 3), date(2026, 9, 22), 31),
        )
    )
    assert result.historical_units == Decimal("87")
    assert result.sales_start_date == date(2026, 7, 3)
    assert result.sales_end_date == date(2026, 9, 22)
    assert result.coverage_status == "complete"


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
