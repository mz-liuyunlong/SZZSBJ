from sqlalchemy import CheckConstraint, UniqueConstraint

import app.modules.data_pages.models  # noqa: F401
from app.db.base import Base


EXPECTED_TABLES = {
    "dim_lingxing_stores",
    "dim_walmart_listings",
    "dim_walmart_advertisers",
    "ref_store_commission_rule_versions",
    "fact_walmart_sales_item_daily",
    "fact_walmart_order_items",
    "fact_walmart_refund_items",
    "fact_walmart_ad_item_sp_daily",
    "mart_daily_sales_item_day",
    "mart_order_profit_sku_day",
    "mart_listing_management_current",
}


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _check_constraint_names(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.name or ""
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_data_pages_tables_use_single_metadata() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_data_pages_dimensions_have_stable_external_keys() -> None:
    assert (
        "source_account_ref",
        "platform_code_raw",
        "store_id",
    ) in _unique_column_sets("dim_lingxing_stores")
    assert (
        "source_account_ref",
        "store_id",
        "item_id",
    ) in _unique_column_sets("dim_walmart_listings")
    assert ("source_account_ref", "advertiser_id") in _unique_column_sets(
        "dim_walmart_advertisers"
    )


def test_data_pages_facts_preserve_lineage_and_business_dates() -> None:
    sales = Base.metadata.tables["fact_walmart_sales_item_daily"].c
    assert {
        "business_date_la",
        "business_timezone",
        "source_raw_request_ref_id",
        "allocation_status",
    } <= set(sales.keys())

    orders = Base.metadata.tables["fact_walmart_order_items"].c
    assert {
        "source_line_hash",
        "source_purchase_timezone",
        "purchase_at_utc",
        "business_date_la",
        "is_sample_order",
    } <= set(orders.keys())

    refunds = Base.metadata.tables["fact_walmart_refund_items"].c
    assert {
        "return_type_raw",
        "refund_at_utc",
        "business_date_la",
        "source_line_hash",
    } <= set(refunds.keys())
    assert "return_type_refund" in _check_constraint_names("fact_walmart_refund_items")


def test_data_pages_marts_snapshot_financial_rules() -> None:
    daily = Base.metadata.tables["mart_daily_sales_item_day"].c
    assert {
        "exchange_rate",
        "fx_date",
        "fx_source",
        "commission_rate",
        "commission_rule_version_id",
        "cost_status",
        "calc_version",
        "calculated_at",
    } <= set(daily.keys())

    order_profit = Base.metadata.tables["mart_order_profit_sku_day"].c
    assert {
        "local_sku",
        "item_ids_json",
        "store_ids_json",
        "gross_profit_amount",
        "gross_margin",
        "roi",
    } <= set(order_profit.keys())


def test_store_commission_rules_are_versioned() -> None:
    rules = Base.metadata.tables["ref_store_commission_rule_versions"].c
    assert {
        "effective_from",
        "effective_to",
        "rule_version",
        "change_reason",
        "approved_by",
        "approved_at",
        "request_id",
    } <= set(rules.keys())
    assert "rate_range" in _check_constraint_names("ref_store_commission_rule_versions")
