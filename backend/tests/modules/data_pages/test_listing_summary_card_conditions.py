"""Regression checks for the shared Listing card predicates; no production database."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.data_pages.monitor_raw_fields import parse_monitor_raw_fields
from app.modules.data_pages.repository import (
    ListingManagementRepository,
    _listing_no_strike_condition,
    _listing_rating_warning_condition,
)


@pytest.mark.parametrize(
    ("rating", "expected"),
    [(None, False), (0, False), (1, True), (3.9, True), (3.99, True), (4, False), (4.5, False)],
)
def test_rating_warning_strict_threshold(rating, expected):
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            actual = connection.scalar(select(_listing_rating_warning_condition(literal(rating))))
        assert bool(actual) is expected
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"hasStrikethrough": False}, True),
        ({"hasStrikethrough": True}, False),
        ({"hasStrikethrough": None}, False),
        ({"hasStrikethrough": "false"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_strike_display_contract(payload, expected):
    assert (parse_monitor_raw_fields(payload).has_strikethrough is False) is expected


def test_strike_predicate_requires_json_boolean_false():
    compiled = select(_listing_no_strike_condition(literal(None))).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)
    assert "jsonb_typeof(jsonb_extract_path(" in sql
    assert "jsonb_extract_path_text(" in sql
    assert "boolean" in compiled.params.values()
    assert "false" in compiled.params.values()


@pytest.mark.parametrize("card", ["rating", "strike"])
def test_summary_and_list_reuse_same_predicate(monkeypatch, card):
    from app.modules.data_pages import repository as module

    name = {
        "rating": "_listing_rating_warning_condition",
        "strike": "_listing_no_strike_condition",
    }[card]
    helper = MagicMock(wraps=getattr(module, name))
    monkeypatch.setattr(module, name, helper)
    session = MagicMock(spec=Session)
    session.execute.return_value.one.return_value = (0, 0, 0, 0, 0, 0, 0)
    repo = ListingManagementRepository(session)
    filters = dict(
        account_refs=frozenset({"primary"}),
        store_id="",
        owner_ref="",
        product_type="",
        status="",
        tag="",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    repo.listing_summary(**filters)
    assert helper.call_count == 1
    repo._filtered_listing_statement(**filters, summary_filter=card)
    assert helper.call_count == 2
