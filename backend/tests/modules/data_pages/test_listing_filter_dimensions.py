"""Read-only regression tests for the Listing filter dimensions."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.data_pages.repository import (
    ListingManagementRepository,
    _listing_buybox_exception_condition,
    _listing_exception_condition,
)
from app.modules.data_pages.schemas import (
    ListingManagementBatchSearchRequest,
    ListingManagementQuery,
)


@pytest.mark.parametrize(
    ("no_strike", "cart", "hijacked", "expected"),
    [
        (False, "NORMAL", False, False),
        (True, "NORMAL", False, True),
        (False, "LOST", False, True),
        (False, "NOT_OWNED", False, True),
        (False, " secondary ", False, True),
        (False, "OTHER", False, True),
        (False, "未拥有", False, True),
        (False, "NOT_FOUND", False, True),
        (False, "CART_NOT_FOUND", False, True),
        (False, "UNAVAILABLE", False, True),
        (False, "OUT_OF_STOCK", False, False),
        (False, "NORMAL", True, True),
        (True, "LOST", True, True),
        (None, None, None, False),
        (None, "FETCH_ERROR", None, False),
        (None, "LOST", None, True),
    ],
)
def test_listing_exception_matches_display(no_strike, cart, hijacked, expected):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        value = connection.scalar(
            select(
                _listing_exception_condition(
                    literal(no_strike),
                    _listing_buybox_exception_condition(literal(cart)),
                    literal(hijacked),
                    literal(10),
                )
            )
        )
    engine.dispose()
    assert value is expected


def test_filter_dimensions_use_shared_scoped_statement():
    repo = ListingManagementRepository(MagicMock(spec=Session))
    statement = repo._filtered_listing_statement(
        account_refs=frozenset({"primary"}),
        store_id="",
        owner_ref="",
        product_type="",
        status="",
        tag="",
        product_tag='["provider,tag", "other"]',
        custom_tag='["custom"]',
        lifecycle="上升期,稳定期",
        grade="A,D",
        summary_filter="listing_exception",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "product_tags_json @>" in sql
    assert "product_custom_tag_assignments" in sql
    assert "product_custom_tags.name IN" in sql
    assert "source_account_ref IN" in sql
    assert "upper(trim(coalesce(" in sql
    assert "provider,tag" in repr(compiled.params)
    assert "上升期" in repr(compiled.params)
    assert "稳定期" in repr(compiled.params)


def test_batch_query_preserves_all_new_filters():
    query = ListingManagementQuery(
        product_tag='["a,b"]',
        custom_tag='["c"]',
        lifecycle="上升期",
        grade="A,D",
        summary_filter="listing_exception",
    )
    actual = ListingManagementBatchSearchRequest(query=query, batch_values=["SKU1"]).as_query()
    assert actual.product_tag == query.product_tag
    assert actual.custom_tag == query.custom_tag
    assert actual.lifecycle == query.lifecycle
    assert actual.grade == query.grade
    assert actual.summary_filter == "listing_exception"
    assert actual.batch_values == "SKU1"


@pytest.mark.parametrize("invalid", ["{}", "[1]", '[""]', "invalid"])
def test_invalid_tag_filter_is_rejected(invalid):
    with pytest.raises(ValidationError):
        ListingManagementQuery(product_tag=invalid)


@pytest.mark.parametrize(
    ("stock", "expected"),
    [(None, False), (-1, False), (0, False), (1, True), (100, True)],
)
def test_listing_exception_requires_positive_stock(stock, expected):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        value = connection.scalar(
            select(
                _listing_exception_condition(
                    literal(True),
                    literal(True),
                    literal(True),
                    literal(stock),
                )
            )
        )
    engine.dispose()
    assert value is expected
