from app.modules.integration_sync.data_pages_catalog import DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY
from app.modules.integration_sync.data_pages_writer_specs import (
    DATA_PAGES_WRITER_SPECS,
    data_pages_writer_parser_keys,
    writer_spec_for,
    writer_target_tables,
)
from app.modules.integration_sync.parsers.lingxing_data_pages import DATA_PAGES_PARSER_SPECS


def test_writer_specs_cover_every_parser_and_sync_interface() -> None:
    assert data_pages_writer_parser_keys() == frozenset(DATA_PAGES_PARSER_SPECS)
    assert data_pages_writer_parser_keys() == frozenset(DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY)
    assert len(DATA_PAGES_WRITER_SPECS) == 7


def test_writer_specs_match_parser_targets_and_unique_keys() -> None:
    for writer_spec in DATA_PAGES_WRITER_SPECS:
        parser_spec = DATA_PAGES_PARSER_SPECS[writer_spec.parser_key]

        assert writer_spec.target_table == parser_spec.target_table
        assert writer_spec.unique_key == parser_spec.unique_key_candidates[0]
        assert writer_spec.source_record_path == parser_spec.record_path
        assert writer_spec.write_mode == "upsert"
        assert writer_spec.idempotency_scope == (
            writer_spec.target_table,
            *writer_spec.unique_key,
        )


def test_writer_specs_keep_required_source_and_lineage_metadata() -> None:
    for writer_spec in DATA_PAGES_WRITER_SPECS:
        parser_spec = DATA_PAGES_PARSER_SPECS[writer_spec.parser_key]
        expected_required = tuple(
            field.target_name for field in parser_spec.fields if field.required
        )

        assert writer_spec.required_source_fields == expected_required
        assert "source_account_ref" in writer_spec.source_metadata_fields
        assert "source_raw_request_ref_id" in writer_spec.source_metadata_fields
        assert "synced_at" in writer_spec.source_metadata_fields
        assert writer_spec.refresh_marts


def test_writer_specs_are_limited_to_dim_and_fact_targets() -> None:
    assert writer_target_tables() == {
        "dim_lingxing_stores",
        "dim_walmart_listings",
        "dim_walmart_advertisers",
        "fact_walmart_sales_item_daily",
        "fact_walmart_order_items",
        "fact_walmart_refund_items",
        "fact_walmart_ad_item_sp_daily",
    }
    assert {spec.target_layer for spec in DATA_PAGES_WRITER_SPECS} == {"DIM", "FACT"}


def test_sales_writer_requires_explicit_sales_date_source() -> None:
    writer_spec = writer_spec_for("sale_stat_page_list")

    assert "date_collect" in writer_spec.required_source_fields
    assert "business_date_la" in writer_spec.unique_key
    assert "mart_daily_sales_item_day" in writer_spec.refresh_marts
    assert "mart_order_profit_sku_day" in writer_spec.refresh_marts


def test_ad_item_writer_refreshes_all_business_marts() -> None:
    writer_spec = writer_spec_for("walmart_ad_item_sp_list")

    assert writer_spec.target_table == "fact_walmart_ad_item_sp_daily"
    assert "advertiser_id" in writer_spec.required_source_fields
    assert writer_spec.refresh_marts == (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    )
