from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint
from app.modules.integration_sync.parsers.lingxing_data_pages import (
    DATA_PAGES_PARSER_SPECS,
    DataPagesParserKey,
)

RequestKind = Literal["offset_page"]


@dataclass(frozen=True, slots=True)
class DataPagesSyncInterfaceSpec:
    """Static catalog contract for DATA-PAGES Lingxing ingestion interfaces."""

    parser_key: DataPagesParserKey
    interface_key: str
    display_name: str
    endpoint_path: LingxingEndpoint
    request_kind: RequestKind
    handler_key: str
    target_table: str
    retention_policy_key: str
    default_page_size: int
    default_max_pages: int
    initial_outbound_enabled: bool = False
    schedule_enabled: bool = False
    notes: tuple[str, ...] = ()


DATA_PAGES_SYNC_INTERFACE_SPECS: Final[tuple[DataPagesSyncInterfaceSpec, ...]] = (
    DataPagesSyncInterfaceSpec(
        parser_key="seller_list_multi_platform",
        interface_key="getSellerList",
        display_name="Lingxing Seller List",
        endpoint_path="/pb/mp/shop/v2/getSellerList",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.get_seller_list.v1",
        target_table="dim_lingxing_stores",
        retention_policy_key="lingxing-data-pages-get-seller-list-v1",
        default_page_size=100,
        default_max_pages=1000,
        notes=("Store metadata is a prerequisite for store-scoped DATA-PAGES joins.",),
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="walmart_listing_list",
        interface_key="walmartListingList",
        display_name="Lingxing Walmart Listing List",
        endpoint_path="/basicOpen/multiplatform/walmart/list",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.walmart_listing_list.v1",
        target_table="dim_walmart_listings",
        retention_policy_key="lingxing-data-pages-walmart-listing-list-v1",
        default_page_size=100,
        default_max_pages=10000,
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="sale_stat_page_list",
        interface_key="saleStatPageList",
        display_name="Lingxing Sale Stat Page List",
        endpoint_path="/basicOpen/platformStatisticsV2/saleStat/pageList",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.sale_stat_page_list.v1",
        target_table="fact_walmart_sales_item_daily",
        retention_policy_key="lingxing-data-pages-sale-stat-page-list-v1",
        default_page_size=100,
        default_max_pages=10000,
        notes=(
            "result_type fan-out must be supplied by request planning, not response inference.",
        ),
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="order_v2_list",
        interface_key="orderV2List",
        display_name="Lingxing Order V2 List",
        endpoint_path="/pb/mp/order/v2/list",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.order_v2_list.v1",
        target_table="fact_walmart_order_items",
        retention_policy_key="lingxing-data-pages-order-v2-list-v1",
        default_page_size=100,
        default_max_pages=10000,
        notes=("date_type is fixed to global_purchase_time for DATA-PAGES profit lineage.",),
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="walmart_return_order_list",
        interface_key="walmartReturnOrderList",
        display_name="Lingxing Walmart Return Order List",
        endpoint_path="/basicOpen/openapi/multiplatform/walmart/returnOrder/list",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.walmart_return_order_list.v1",
        target_table="fact_walmart_refund_items",
        retention_policy_key="lingxing-data-pages-walmart-return-order-list-v1",
        default_page_size=100,
        default_max_pages=10000,
        notes=("Only returnType=REFUND records are retained for DATA-PAGES marts.",),
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="walmart_advertiser_list",
        interface_key="walmartAdvertiserList",
        display_name="Lingxing Walmart Advertiser List",
        endpoint_path="/basicOpen/adReport/advertiser/list",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.walmart_advertiser_list.v1",
        target_table="dim_walmart_advertisers",
        retention_policy_key="lingxing-data-pages-walmart-advertiser-list-v1",
        default_page_size=100,
        default_max_pages=1000,
        notes=("Advertiser IDs are prerequisites for Walmart SP ad item report requests.",),
    ),
    DataPagesSyncInterfaceSpec(
        parser_key="walmart_ad_item_sp_list",
        interface_key="walmartAdItemSpList",
        display_name="Lingxing Walmart SP Ad Item Report",
        endpoint_path="/basicOpen/multiplatform/ads/reportAdItemSpList",
        request_kind="offset_page",
        handler_key="lingxing.data_pages.walmart_ad_item_sp_list.v1",
        target_table="fact_walmart_ad_item_sp_daily",
        retention_policy_key="lingxing-data-pages-walmart-ad-item-sp-list-v1",
        default_page_size=100,
        default_max_pages=10000,
        notes=("Request planning must use advertiser IDs captured from advertiser/list.",),
    ),
)

DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY: Final = {
    spec.parser_key: spec for spec in DATA_PAGES_SYNC_INTERFACE_SPECS
}


def data_pages_parser_keys() -> frozenset[DataPagesParserKey]:
    return frozenset(DATA_PAGES_PARSER_SPECS)


def data_pages_sync_parser_keys() -> frozenset[DataPagesParserKey]:
    return frozenset(DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY)
