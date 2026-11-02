"""CSV exports must never execute untrusted Listing text in spreadsheet software."""

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.modules.data_pages.schemas import ListingManagementQuery
from app.modules.data_pages.service import ListingManagementService


def test_listing_csv_text_formula_prefixes_are_escaped() -> None:
    for payload in (
        "=1+1",
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        "  =HYPERLINK(1,2)",
        "\ufeff=HYPERLINK(1,2)",
        "\u200b =1+1",
        " \ufeff\u200b =1+1",
    ):
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


def test_listing_csv_start_date_uses_only_first_observed_wfs_stock() -> None:
    service = ListingManagementService(MagicMock())
    service.tag_repository.tags_for_listing_rows = MagicMock(return_value={})
    service.repository.archive_states_for_listing_rows = MagicMock(return_value={})
    listing = SimpleNamespace(
        id=UUID(int=1),
        source_account_ref="account",
        item_id="item",
    )
    service._to_read = lambda *_args, **_kwargs: SimpleNamespace(
        launch_date_cn=date(2026, 1, 15),
        listing_start_source_raw="2026-01-10 09:31:47",
    )
    assert list(
        csv.reader(
            StringIO(
                service.export_listing_csv(
                    ListingManagementQuery(),
                    frozenset({"account"}),
                    columns="listed_at",
                    _rows=[listing],
                )
            )
        )
    ) == [["上架时间"], ["2026-01-15"]]

    service._to_read = lambda *_args, **_kwargs: SimpleNamespace(
        launch_date_cn=None,
        listing_start_source_raw="2026-01-10 09:31:47",
    )
    assert list(
        csv.reader(
            StringIO(
                service.export_listing_csv(
                    ListingManagementQuery(),
                    frozenset({"account"}),
                    columns="listed_at",
                    _rows=[listing],
                )
            )
        )
    ) == [["上架时间"], [""]]


def test_listing_csv_removed_date_column_does_not_export_every_column() -> None:
    service = ListingManagementService(MagicMock())
    service.tag_repository.tags_for_listing_rows = MagicMock(return_value={})
    service.repository.archive_states_for_listing_rows = MagicMock(return_value={})
    with pytest.raises(ValueError, match="Listing导出列无效"):
        service.export_listing_csv(
            ListingManagementQuery(),
            frozenset({"account"}),
            columns="listing_start_source_raw",
            _rows=[],
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
