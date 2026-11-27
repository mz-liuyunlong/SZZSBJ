"""Read-only regression tests for all Listing exact-value facets."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    column,
    create_engine,
    select,
    table,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.data_pages.listing_exact_facets import (
    FACET_FIELDS,
    Facet,
    facet_option,
    facet_option_statement,
    facet_predicate,
    listing_facet,
    parse_exact_filters,
)
from app.modules.data_pages.repository import (
    _listing_buybox_exception_condition,
    _listing_exception_condition,
    _listing_no_strike_condition,
)
from app.modules.data_pages.schemas import (
    ListingManagementBatchSearchRequest,
    ListingManagementExactRequest,
    ListingManagementFacetRequest,
    ListingManagementQuery,
)


def projection():
    texts = (
        "id source_account_ref store_id store_name owner_name owner_ref item_id local_sku "
        "msku local_name effective_title effective_category disabled_reason effective_brand "
        "effective_walmart_seller gtin effective_lifecycle_status product_grade picture_url "
        "effective_buybox_status fulfillment_type_name fulfillment_type"
    )
    numbers = (
        "effective_strike_price_amount effective_sale_price_amount ad_spend_30d_amount "
        "effective_average_rating sales_30d inbound_quantity wfs_available_quantity"
    )
    return table(
        "scoped_listing_projection",
        *[column(name, String()) for name in texts.split()],
        *[column(name, Numeric()) for name in numbers.split()],
        column("effective_review_count", Integer()),
        column("first_wfs_available_date_la", Date()),
        column("monitor_checked_at", DateTime(timezone=True)),
        column("effective_is_hijacked", Boolean()),
        column("monitor_raw_parsed", JSONB()),
        column("product_tags_json", JSONB()),
    )


@pytest.mark.parametrize("field", FACET_FIELDS)
def test_each_field_compiles_count_and_exact_predicate(field):
    base = projection()
    facet = listing_facet(
        base.c,
        field,
        _listing_exception_condition,
        _listing_buybox_exception_condition,
        _listing_no_strike_condition,
    )
    options = str(facet_option_statement(base, facet, field).compile(dialect=postgresql.dialect()))
    predicate = select(base.c.id).where(facet_predicate(facet, ['v:"actual"', "n:"]))
    sql = str(predicate.compile(dialect=postgresql.dialect()))
    assert "count(DISTINCT" in options
    assert "GROUP BY" in options
    assert "scoped_listing_projection" in sql
    assert "LIKE" not in sql.upper()


def test_exact_numeric_null_and_multi_field_and():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    rows = Table(
        "listings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("stock", Integer),
        Column("score", String),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            rows.insert(),
            [
                {"id": 1, "stock": 0, "score": "3.9"},
                {"id": 2, "stock": 10, "score": "4.0"},
                {"id": 3, "stock": 11, "score": "4.0"},
                {"id": 4, "stock": None, "score": "3.9"},
                {"id": 5, "stock": 10, "score": "4.5"},
            ],
        )
        stock = Facet(scalar=rows.c.stock)
        score = Facet(scalar=rows.c.score)
        predicate = (
            select(rows.c.id)
            .where(
                facet_predicate(stock, ['v:"0"', 'v:"10"', "n:"]),
                facet_predicate(score, ['v:"3.9"', 'v:"4.0"']),
            )
            .order_by(rows.c.id)
        )
        assert connection.scalars(predicate).all() == [1, 2, 4]
        actual = connection.execute(
            facet_option_statement(rows, stock, "wfsAvailableInventory")
        ).all()
        assert actual == [("0", 1), ("10", 2), ("11", 1), (None, 1)]
    engine.dispose()


def test_token_preserves_commas_unicode_whitespace_and_missing():
    item = facet_option("title", "  Red, 红色  ", 3)
    assert item["label"] == "  Red, 红色  "
    assert parse_exact_filters(json.dumps({"title": [item["value"], item["value"], "n:"]})) == {
        "title": [item["value"], "n:"],
    }
    assert facet_option("rating", "3.9950", 1)["label"] == "3.995"
    assert facet_option("rating", None, 1)["value"] == "n:"


@pytest.mark.parametrize("raw", ["[]", '{"invalid":[]}', '{"sku":["raw"]}', '{"sku":["v:1"]}'])
def test_bad_filters_rejected(raw):
    with pytest.raises(ValidationError):
        ListingManagementQuery(exact_filters=raw)


def test_post_body_allows_empty_batch_only_on_new_request():
    raw = json.dumps({"sku": ['v:"SKU-1"']})
    request = ListingManagementExactRequest(query=ListingManagementQuery(exact_filters=raw))
    assert request.as_query().exact_filters == raw
    assert request.as_query().batch_values == ""
    batch = ListingManagementExactRequest(query=request.query, batch_values=["sku-a", "sku-b"])
    assert batch.as_query().batch_values == "sku-a,sku-b"
    assert batch.as_query().exact_filters == raw
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(query=request.query, batch_values=[])
    with pytest.raises(ValidationError):
        ListingManagementFacetRequest(field="invalid")


def test_batch_facet_request_validates_fields_and_preserves_scope():
    from app.modules.data_pages.schemas import ListingManagementFacetBatchRequest

    request = ListingManagementFacetBatchRequest(
        query=ListingManagementQuery(summary_filter="online"),
        fields={"rating": 0, "brand": 500},
        batch_values=["sku-a"],
    )
    assert request.fields == {"rating": 0, "brand": 500}
    assert request.as_query().summary_filter == "online"
    assert request.as_query().batch_values == "sku-a"
    for invalid in ({}, {"invalid": 0}, {"rating": -1}, {"rating": 1_000_001}):
        with pytest.raises(ValidationError):
            ListingManagementFacetBatchRequest(fields=invalid)


def test_complete_facet_batch_uses_one_materialized_scope_and_all_fields():
    from app.modules.data_pages.listing_exact_facets import complete_facet_batch_statement

    base = projection()
    query = complete_facet_batch_statement(
        select(base),
        ["rating", "brand", "keyFeatures", "archiveReason"],
        {"rating": ['v:"4"'], "brand": ['v:"Example"']},
        _listing_exception_condition,
        _listing_buybox_exception_condition,
        _listing_no_strike_condition,
    )
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert sql.count("AS MATERIALIZED") == 1
    assert sql.count("UNION ALL") == 3
    assert "LATERAL" in sql


def test_complete_facet_batch_options_preserve_exact_order_and_nulls():
    from app.modules.data_pages.listing_exact_facets import complete_facet_batch_items

    items = complete_facet_batch_items(
        ["rating", "checkedAt"],
        [
            ("rating", "10", 2),
            ("rating", None, 1),
            ("rating", "2.5", 3),
            ("checkedAt", "2026-11-01", 2),
            ("checkedAt", "2026-11-24", 1),
        ],
    )
    assert [item["label"] for item in items["rating"]["options"]] == ["2.5", "10", "无评分"]
    assert [item["label"] for item in items["checkedAt"]["options"]] == ["2026-11-24", "2026-11-01"]
    assert not items["rating"]["has_more"]


def test_batch_facet_projection_covers_all_supported_fields():
    from app.modules.data_pages.listing_exact_facets import (
        batch_facet_projection,
        complete_facet_batch_statement,
    )

    statement = select(projection())
    for field in FACET_FIELDS:
        narrowed = batch_facet_projection(statement, [field], {})
        assert "id" in narrowed.selected_columns.keys()
        query = complete_facet_batch_statement(
            statement,
            [field],
            {},
            _listing_exception_condition,
            _listing_buybox_exception_condition,
            _listing_no_strike_condition,
        )
        assert "AS MATERIALIZED" in str(query.compile(dialect=postgresql.dialect()))
    narrow = batch_facet_projection(statement, ["rating"], {"brand": ['v:"Example"']})
    assert set(narrow.selected_columns.keys()) == {
        "id",
        "monitor_raw_parsed",
        "effective_average_rating",
        "effective_brand",
    }


def test_compact_facet_label_preserves_exact_token_and_nonredundant_labels():
    import json

    from app.modules.data_pages.listing_exact_facets import compact_facet_label

    label = 'Long, "quoted" 商品描述 ' * 10
    token = "v:" + json.dumps(label, ensure_ascii=False)
    assert compact_facet_label(token, label) == ""
    assert json.loads(token[2:]) == label
    assert compact_facet_label(token, "Different label") == "Different label"
    assert compact_facet_label('v:"4.0000"', "4") == "4"
    assert compact_facet_label("n:", "无数据") == "无数据"
