"""CSV exports must never execute untrusted Listing text in spreadsheet software."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.modules.data_pages.schemas import ListingManagementQuery
from app.modules.data_pages.service import ListingManagementService


def test_listing_csv_text_formula_prefixes_are_escaped() -> None:
    for payload in ("=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)", "  =HYPERLINK(1,2)"):
        assert ListingManagementService._csv_value(payload).startswith("'")


def test_listing_csv_numeric_and_plain_text_values_are_preserved() -> None:
    assert ListingManagementService._csv_value(Decimal("-12.50")) == "-12.50"
    assert ListingManagementService._csv_value("Product title") == "Product title"
    assert ListingManagementService._csv_value(None) == ""


@pytest.mark.parametrize(
    "value",
    [
        ["=HYPERLINK(1,2)"],
        ["+SUM(1,2)", "safe"],
        ["-1+2"],
        ["@SUM(1,2)"],
        ["\t=HYPERLINK(1,2)"],
        ["\r=HYPERLINK(1,2)"],
        ["\n=HYPERLINK(1,2)"],
    ],
)
def test_listing_csv_list_text_formula_prefixes_are_escaped(value: list[str]) -> None:
    assert ListingManagementService._csv_value(value).startswith("'")


def test_listing_csv_start_date_matches_raw_display_fallback() -> None:
    assert ListingManagementService._listing_start_csv_value(None, "2026-01-15 09:31:47") == (
        "2026-01-15"
    )
    assert ListingManagementService._listing_start_csv_value(None, "unverified") == "unverified"
    assert (
        ListingManagementService._listing_start_csv_value(
            datetime(2026, 1, 16, 0, 30, tzinfo=timezone(timedelta(hours=8))), None
        )
        == "2026-01-15"
    )


def test_large_listing_export_streams_all_rows_with_one_header() -> None:
    service = ListingManagementService(MagicMock())
    service.repository.iter_export_listing_batches = MagicMock(
        return_value=(
            [
                SimpleNamespace(id=UUID(int=i + 1), source_account_ref="account", item_id=str(i))
                for i in range(start, min(start + 500, 10001))
            ]
            for start in range(0, 10001, 500)
        )
    )
    service.repository.archive_states_for_listing_rows = MagicMock(return_value={})
    service.tag_repository.tags_for_listing_rows = MagicMock(return_value={})
    service._to_read = lambda row, *_args, **_kwargs: SimpleNamespace(local_sku=row.item_id)

    chunks = list(
        service.iter_export_listing_csv(
            ListingManagementQuery(), frozenset({"account"}), columns="sku"
        )
    )
    exported = b"".join(chunks).decode("utf-8-sig")
    assert exported.count("SKU\r\n") == 1
    assert len(exported.splitlines()) == 10002
    assert exported.splitlines()[-1] == "10000"
