from app.modules.integration_sync.data_pages_catalog import (
    DATA_PAGES_SYNC_INTERFACE_SPECS,
    data_pages_parser_keys,
    data_pages_sync_parser_keys,
)
from app.modules.integration_sync.parsers.lingxing_data_pages import DATA_PAGES_PARSER_SPECS


EXPECTED_PARSER_KEYS = {
    "seller_list_multi_platform",
    "walmart_listing_list",
    "sale_stat_page_list",
    "order_v2_list",
    "walmart_return_order_list",
    "walmart_advertiser_list",
    "walmart_ad_item_sp_list",
}


def test_data_pages_sync_catalog_covers_all_parser_specs() -> None:
    assert data_pages_parser_keys() == EXPECTED_PARSER_KEYS
    assert data_pages_sync_parser_keys() == EXPECTED_PARSER_KEYS


def test_data_pages_sync_catalog_matches_parser_contracts() -> None:
    for spec in DATA_PAGES_SYNC_INTERFACE_SPECS:
        parser_spec = DATA_PAGES_PARSER_SPECS[spec.parser_key]

        assert spec.endpoint_path == parser_spec.api_path
        assert spec.target_table == parser_spec.target_table
        assert spec.request_kind == "offset_page"
        assert spec.default_page_size > 0
        assert spec.default_max_pages > 0
        assert spec.initial_outbound_enabled is False
        assert spec.schedule_enabled is False


def test_data_pages_sync_catalog_has_stable_unique_keys() -> None:
    assert len({spec.parser_key for spec in DATA_PAGES_SYNC_INTERFACE_SPECS}) == 7
    assert len({spec.interface_key for spec in DATA_PAGES_SYNC_INTERFACE_SPECS}) == 7
    assert len({spec.handler_key for spec in DATA_PAGES_SYNC_INTERFACE_SPECS}) == 7
    assert len({spec.retention_policy_key for spec in DATA_PAGES_SYNC_INTERFACE_SPECS}) == 7

    for spec in DATA_PAGES_SYNC_INTERFACE_SPECS:
        assert spec.handler_key.startswith("lingxing.data_pages.")
        assert spec.handler_key.endswith(".v1")
        assert spec.retention_policy_key.startswith("lingxing-data-pages-")
        assert spec.retention_policy_key.endswith("-v1")
