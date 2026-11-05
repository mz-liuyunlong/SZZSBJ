"""POST transport accepts 1000 valid batch identifiers without the old GET size limit."""

import pytest
from pydantic import ValidationError

from app.modules.data_pages.schemas import ListingManagementBatchSearchRequest


def test_batch_1000_max_length_values_are_accepted():
    values = [f"SKU{i:04d}" + ("x" * 121) for i in range(1000)]
    assert all(len(v) == 128 for v in values)
    payload = ListingManagementBatchSearchRequest(
        query={"search_field": "sku", "page": 2, "page_size": 50},
        batch_values=values,
    )
    query = payload.as_query()
    assert query.page == 2
    assert query.page_size == 50
    assert len(query.batch_values) > 32768
    assert query.batch_values.split(",") == values


def test_reject_more_than_1000_identifiers():
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(batch_values=[f"SKU{i}" for i in range(1001)])


def test_reject_oversized_or_comma_identifier():
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(batch_values=["X" * 129])
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(batch_values=["SKU,unsafe"])


def test_duplicate_values_are_deduplicated_without_changing_order():
    payload = ListingManagementBatchSearchRequest(batch_values=["sku-1", "sku-2", "sku-1"])
    assert payload.as_query().batch_values == "sku-1,sku-2"
