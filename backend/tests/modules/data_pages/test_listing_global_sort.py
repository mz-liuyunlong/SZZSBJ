"""Listing full-result ordering; SQL compilation and isolated execution tests."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.data_pages.listing_sort import (
    LISTING_SORT_FIELDS,
    listing_order_columns,
    parse_listing_sort,
)
from app.modules.data_pages.repository import (
    ListingManagementRepository,
    _listing_buybox_exception_condition,
    _listing_exception_condition,
    _listing_no_strike_condition,
)
from app.modules.data_pages.schemas import (
    ListingManagementBatchSearchRequest,
    ListingManagementExactRequest,
    ListingManagementQuery,
)


def order(c, raw):
    return listing_order_columns(
        c,
        raw,
        _listing_exception_condition,
        _listing_buybox_exception_condition,
        _listing_no_strike_condition,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "sku:asc",
        "rating:up",
        "rating:asc,rating:desc",
        "rating:asc;DROP",
        "rating",
        "rating:asc,",
        "rating:ASC",
    ],
)
def test_invalid_order_rejected(raw):
    with pytest.raises(ValidationError):
        ListingManagementQuery(sort_by=raw)


def test_transport_keeps_sort_priority_with_exact_and_batch_filters():
    raw = "sales90Days:asc,rating:desc"
    query = ListingManagementQuery(sort_by=raw, exact_filters='{"rating":["n:"]}')
    assert parse_listing_sort(raw) == [("sales90Days", "asc"), ("rating", "desc")]
    assert ListingManagementExactRequest(query=query).as_query().sort_by == raw
    batch = ListingManagementBatchSearchRequest(query=query, batch_values=["sku-a"])
    assert batch.as_query().sort_by == raw
    assert batch.as_query().exact_filters == query.exact_filters


@pytest.mark.parametrize("field", sorted(LISTING_SORT_FIELDS))
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_all_order_expressions_compile_before_pagination(field, direction):
    repository = ListingManagementRepository(MagicMock(spec=Session))
    statement = repository._filtered_listing_statement(
        account_refs=frozenset({"test-account"}),
        store_id="",
        owner_ref="",
        product_type="",
        status="",
        tag="",
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    sql = str(
        statement.order_by(*order(statement.selected_columns, f"{field}:{direction}"))
        .offset(50)
        .limit(50)
        .compile(dialect=postgresql.dialect())
    )
    clause = sql.rsplit("ORDER BY", 1)[-1]
    assert direction.upper() + " NULLS LAST" in clause
    assert "mart_listing_management_current.id ASC" in clause
    assert clause.index("NULLS LAST") < clause.index("LIMIT")


def test_numeric_multisort_null_last_and_cross_page():
    metadata = MetaData()
    rows = Table(
        "sort_rows",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("sales_30d", Integer),
        Column("effective_average_rating", Integer),
        Column("monitor_raw_parsed", String),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                rows.insert(),
                [
                    {"id": 1, "sales_30d": 0, "effective_average_rating": 4},
                    {"id": 2, "sales_30d": 0, "effective_average_rating": 2},
                    {"id": 3, "sales_30d": 5, "effective_average_rating": 1},
                    {"id": 4, "sales_30d": None, "effective_average_rating": None},
                    {"id": 5, "sales_30d": 0, "effective_average_rating": 2},
                ],
            )
            asc = select(rows.c.id).order_by(*order(rows.c, "sales90Days:asc,rating:asc"))
            desc = select(rows.c.id).order_by(*order(rows.c, "sales90Days:desc,rating:desc"))
            assert conn.scalars(asc.limit(2)).all() == [2, 5]
            assert conn.scalars(asc.offset(2)).all() == [1, 3, 4]
            assert conn.scalars(desc).all() == [3, 1, 2, 5, 4]
    finally:
        engine.dispose()


def test_saved_grade_lifecycle_rank_and_default():
    metadata = MetaData()
    rows = Table(
        "sort_rows",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("product_grade", String),
        Column("effective_lifecycle_status", String),
        Column("wfs_available_quantity", Integer),
        Column("store_name", String),
        Column("local_sku", String),
        Column("item_id", String),
        Column("monitor_raw_parsed", String),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                rows.insert(),
                [
                    {
                        "id": 1,
                        "product_grade": "A",
                        "effective_lifecycle_status": "上升期",
                        "wfs_available_quantity": 3,
                    },
                    {
                        "id": 2,
                        "product_grade": "D",
                        "effective_lifecycle_status": "断货期",
                        "wfs_available_quantity": 0,
                    },
                    {
                        "id": 3,
                        "product_grade": None,
                        "effective_lifecycle_status": None,
                        "wfs_available_quantity": 5,
                    },
                ],
            )
            for raw, expected in (
                ("productGrade:asc", [1, 2, 3]),
                ("productGrade:desc", [2, 1, 3]),
                ("lifecycle:asc", [2, 1, 3]),
                ("", [3, 1, 2]),
            ):
                statement = select(rows.c.id).order_by(*order(rows.c, raw))
                assert conn.scalars(statement).all() == expected
    finally:
        engine.dispose()
