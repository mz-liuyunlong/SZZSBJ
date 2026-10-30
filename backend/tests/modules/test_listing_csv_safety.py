"""CSV exports must never execute untrusted Listing text in spreadsheet software."""

from decimal import Decimal

from app.modules.data_pages.service import ListingManagementService


def test_listing_csv_text_formula_prefixes_are_escaped() -> None:
    for payload in ("=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)", "  =HYPERLINK(1,2)"):
        assert ListingManagementService._csv_value(payload).startswith("'")


def test_listing_csv_numeric_and_plain_text_values_are_preserved() -> None:
    assert ListingManagementService._csv_value(Decimal("-12.50")) == "-12.50"
    assert ListingManagementService._csv_value("Product title") == "Product title"
    assert ListingManagementService._csv_value(None) == ""
