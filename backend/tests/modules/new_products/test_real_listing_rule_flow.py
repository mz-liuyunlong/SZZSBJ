"""Isolated contract tests: no live DB credentials, network, DDL, or writes."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.api import ApiError
from app.modules.new_products.read_source import source_url
from app.modules.new_products.repository import SAMPLE_TAG, _NewProductListingRepository
from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS, validate
from app.modules.new_products.scoring import evaluate


def test_product_tag_is_jsonb_and_is_applied_before_pagination():
    repo = _NewProductListingRepository(MagicMock())
    statement = repo._filtered_listing_statement(
        account_refs=frozenset({"source-A"}),
        store_id="",
        owner_ref="",
        product_type="",
        status="",
        tag="ignored-custom-tag",
        archive_status="",
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "product_tags_json" in sql and "@>" in sql
    assert "tags_json" not in str(statement.whereclause) or "product_tags_json" in str(
        statement.whereclause
    )
    assert SAMPLE_TAG == "小批量测品"


def cfg():
    return {
        "weights": deepcopy(DEFAULT_WEIGHTS),
        "confirmedScoring": deepcopy(DEFAULT_PARAMETERS),
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
        "quantities": {
            "S": [400, 600],
            "A": [300, 500],
            "B": [200, 400],
            "C": [150, 250],
            "D": [0, 0],
            "Pass": [0, 0],
        },
        "scoreCriteria": {"market": ["evaluation"] * 5},
        "penalties": [],
        "vetoes": [],
    }


def test_grade_bands_are_enforced_on_server():
    c = cfg()
    assert validate("performance", c)
    c["gradeBands"] = {
        "S": [9.9, 10],
        "A": [8.9, 9.89],
        "B": [7.9, 8.89],
        "C": [6.9, 7.89],
        "D": [0, 6.89],
    }
    assert validate("performance", c)
    facts = {
        "market_score": 8,
        "first_order_day": 3,
        "elapsed_days": 14,
        "effective_orders_14d": 20,
        "valid_orders_14d": 20,
        "valid_units_14d": 20,
        "single_unit_orders_14d": 18,
        "ad_status": "not_run",
        "roi": Decimal("1.5"),
        "gross_margin_pct": Decimal("25"),
    }
    score = evaluate(facts, c, 17)
    assert score["rule_version"] == 17
    assert score["grade"] is not None
    assert score["grade"] == "A"
    grade = score["grade"]
    assert Decimal(str(c["gradeBands"][grade][0])) <= Decimal(score["total"]).quantize(
        Decimal(".01")
    )


def test_invalid_grade_gap_rejected():
    c = cfg()
    c["gradeBands"]["B"][1] = 7.98
    with pytest.raises(ValueError):
        validate("performance", c)


def test_local_read_requires_real_source(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    with pytest.raises(ApiError) as exc:
        source_url()
    assert exc.value.status_code == 503


def test_stage_one_base_mart_page_avoids_heavy_listing_joins():
    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    session.scalar.return_value = 0
    session.scalars.return_value.all.return_value = []
    repo = NewProductRepository(session)

    data, total, last = repo.page(frozenset({"source-A"}), page=1, page_size=200)

    assert total == 0 and last is None and data.items == []
    count_sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    rows_sql = str(session.scalars.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "product_tags_json" in count_sql and "@>" in count_sql
    assert "source_account_ref" in count_sql
    assert "mart_listing_management_current" in rows_sql
    assert " JOIN " not in count_sql.upper()
    assert " JOIN " not in rows_sql.upper()
    assert session.execute.call_count == 0


def test_stage_one_page_enriches_owner_and_first_wfs_in_bounded_batches():
    from datetime import date

    from app.modules.data_pages.schemas import ListingManagementItemRead
    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    session.scalar.side_effect = [2, "listing_wfs_first_stock_la_locked"]
    listing_rows = [
        SimpleNamespace(
            source_account_ref="primary", store_id="s1", item_id="i1", local_sku="SKU1"
        ),
        SimpleNamespace(
            source_account_ref="primary", store_id="s1", item_id="i2", local_sku="SKU2"
        ),
    ]
    session.scalars.return_value.all.return_value = listing_rows
    session.execute.side_effect = [
        SimpleNamespace(
            mappings=lambda: [
                {
                    "source_account_ref": "primary",
                    "lingxing_sku_code": "SKU1",
                    "owner_uid": "u1",
                    "owner_name": "张三",
                    "developer_uid": None,
                    "developer_name": None,
                },
            ]
        ),
        SimpleNamespace(
            mappings=lambda: [
                {
                    "source_account_ref": "primary",
                    "store_id": "s1",
                    "item_id": "i1",
                    "first_wfs_available_date_la": date(2026, 11, 1),
                },
            ]
        ),
    ]
    repo = NewProductRepository(session)
    repo.listings._to_read = lambda row: ListingManagementItemRead.model_construct(
        source_account_ref=row.source_account_ref,
        store_id=row.store_id,
        item_id=row.item_id,
        local_sku=row.local_sku,
        owner_name=None,
        owner_uid=None,
        product_developer_name=None,
        product_developer_uid=None,
        first_wfs_available_date_la=None,
    )
    page, total, _ = repo.page(frozenset({"primary"}), page=1, page_size=200)
    assert total == 2 and len(page.items) == 2
    assert page.items[0].owner_name == "张三"
    assert page.items[0].first_wfs_available_date_la == date(2026, 11, 1)
    assert page.items[1].owner_name is None
    assert page.items[1].first_wfs_available_date_la is None
    assert session.execute.call_count == 2
    owner_sql = str(session.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    first_sql = str(session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "dwd_lingxing_sku_product_info_current" in owner_sql
    assert "listing_wfs_first_stock_la_locked" in first_sql
    assert "fact_walmart_order_items" not in owner_sql + first_sql
    assert "mart_daily_sales_item_day" not in owner_sql + first_sql


def test_stage_one_missing_locked_stock_table_uses_first_positive_inventory_date():
    from datetime import date

    from app.modules.data_pages.schemas import ListingManagementItemRead
    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    session.scalar.side_effect = [1, None]
    row = SimpleNamespace(source_account_ref="primary", store_id="s1", item_id="i1", local_sku=None)
    session.scalars.return_value.all.return_value = [row]
    session.execute.return_value.mappings.return_value = [
        {
            "source_account_ref": "primary",
            "store_id": "s1",
            "item_id": "i1",
            "first_wfs_available_date_la": date(2026, 10, 1),
        }
    ]
    repo = NewProductRepository(session)
    repo.listings._to_read = lambda x: ListingManagementItemRead.model_construct(
        source_account_ref=x.source_account_ref,
        store_id=x.store_id,
        item_id=x.item_id,
        local_sku=x.local_sku,
        owner_name=None,
        owner_uid=None,
        product_developer_name=None,
        product_developer_uid=None,
        first_wfs_available_date_la=None,
    )
    page, _, _ = repo.page(frozenset({"primary"}))
    assert page.items[0].first_wfs_available_date_la == date(2026, 10, 1)
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "fact_walmart_listing_inventory_daily" in sql
    assert "wfs_available_quantity" in sql
    assert "fact_walmart_order_items" not in sql


def test_first_order_date_reads_daily_sales_for_scoped_listing_keys_only():
    from datetime import date

    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    session.execute.return_value.mappings.return_value = [
        {
            "source_account_ref": "primary",
            "store_id": "store1",
            "item_id": "i1",
            "first_order_date": date(2026, 10, 15),
        },
    ]
    repo = NewProductRepository(session)
    items = [
        SimpleNamespace(source_account_ref="primary", store_id="store1", item_id="i1"),
        SimpleNamespace(source_account_ref="primary", store_id="store1", item_id="i2"),
    ]
    dates = repo.first_order_dates(items)
    assert dates == {("primary", "store1", "i1"): date(2026, 10, 15)}
    session.execute.assert_called_once()
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "mart_daily_sales_item_day" in sql
    assert "business_date_la" in sql
    assert "order_count >" in sql
    assert "source_account_ref" in sql and "store_id" in sql and "item_id" in sql
    assert "GROUP BY" in sql
    assert "fact_walmart_order_items" not in sql
    assert "INSERT" not in sql.upper() and "UPDATE" not in sql.upper()


def test_first_order_date_empty_page_does_not_access_database():
    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    repo = NewProductRepository(session)
    assert repo.first_order_dates([]) == {}
    session.execute.assert_not_called()


def test_preview_four_ids_requires_explicit_local_environment(monkeypatch):
    from app.core.api import ApiError
    from app.modules.new_products.service import local_preview_item_ids

    monkeypatch.delenv("PR337_LOCAL_PREVIEW_ITEM_IDS", raising=False)
    assert local_preview_item_ids() is None
    monkeypatch.setenv(
        "PR337_LOCAL_PREVIEW_ITEM_IDS", "20874953767,20881463249,20859269992,20858150090"
    )
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ApiError):
        local_preview_item_ids()
    monkeypatch.setenv("APP_ENV", "local")
    assert local_preview_item_ids() == frozenset(
        {"20874953767", "20881463249", "20859269992", "20858150090"}
    )
    monkeypatch.setenv(
        "PR337_LOCAL_PREVIEW_ITEM_IDS", "20874953767,20874953767,20859269992,20858150090"
    )
    with pytest.raises(ApiError):
        local_preview_item_ids()


def test_preview_database_filter_preserves_account_and_tag(monkeypatch):
    from app.modules.new_products.repository import NewProductRepository

    session = MagicMock()
    session.scalar.return_value = 0
    session.scalars.return_value.all.return_value = []
    repo = NewProductRepository(session)
    repo.page(frozenset({"primary"}), item_ids={"20874953767", "20881463249"})
    sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "item_id IN" in sql and "product_tags_json" in sql
    assert "source_account_ref" in sql
    assert " JOIN " not in sql.upper()
