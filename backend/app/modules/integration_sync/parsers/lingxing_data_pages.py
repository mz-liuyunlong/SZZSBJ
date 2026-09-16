from dataclasses import dataclass
from typing import Literal

from app.integrations.lingxing.client import LingxingEndpoint

type DataPagesParserKey = Literal[
    "seller_list_multi_platform",
    "walmart_listing_list",
    "sale_stat_page_list",
    "order_v2_list",
    "walmart_return_order_list",
    "walmart_advertiser_list",
    "walmart_ad_item_sp_list",
]


@dataclass(frozen=True, slots=True)
class ParserFieldSpec:
    target_name: str
    source_path: str
    required: bool = False
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DataPagesParserSpec:
    parser_key: DataPagesParserKey
    api_path: LingxingEndpoint
    record_path: str
    target_table: str
    unique_key_candidates: tuple[tuple[str, ...], ...]
    fields: tuple[ParserFieldSpec, ...]
    skip_rules: tuple[str, ...]
    warnings: tuple[str, ...] = ()


DATA_PAGES_PARSER_SPECS: dict[DataPagesParserKey, DataPagesParserSpec] = {
    "seller_list_multi_platform": DataPagesParserSpec(
        parser_key="seller_list_multi_platform",
        api_path="/pb/mp/shop/v2/getSellerList",
        record_path="data[].list[]",
        target_table="dim_lingxing_stores",
        unique_key_candidates=(("source_account_ref", "platform_code_raw", "store_id"),),
        fields=(
            ParserFieldSpec("platform_name_raw", "data[].list[].platform_name"),
            ParserFieldSpec("platform_code_raw", "data[].list[].platform_code", required=True),
            ParserFieldSpec("store_id", "data[].list[].store_id", required=True),
            ParserFieldSpec("store_name", "data[].list[].store_name"),
            ParserFieldSpec("sid", "data[].list[].sid"),
            ParserFieldSpec("currency_code_raw", "data[].list[].currency"),
            ParserFieldSpec("raw_status", "data[].list[].status"),
            ParserFieldSpec("is_sync_raw", "data[].list[].is_sync"),
        ),
        skip_rules=(
            "store_id is required for DATA-PAGES joins",
            "platform_code values outside Walmart may be stored but are not used by DATA-PAGES-1 MARTs",
        ),
    ),
    "walmart_listing_list": DataPagesParserSpec(
        parser_key="walmart_listing_list",
        api_path="/basicOpen/multiplatform/walmart/list",
        record_path="data.list[]",
        target_table="dim_walmart_listings",
        unique_key_candidates=(("source_account_ref", "store_id", "item_id"),),
        fields=(
            ParserFieldSpec("item_id", "data.list[].item_id", required=True),
            ParserFieldSpec("picture_url", "data.list[].picture_url"),
            ParserFieldSpec("msku", "data.list[].msku"),
            ParserFieldSpec("local_sku", "data.list[].local_sku"),
            ParserFieldSpec("local_name", "data.list[].local_name"),
            ParserFieldSpec("store_id", "data.list[].store_id", required=True),
            ParserFieldSpec("store_name", "data.list[].store_name"),
            ParserFieldSpec("title", "data.list[].title"),
            ParserFieldSpec("price_amount", "data.list[].price"),
            ParserFieldSpec("currency_symbol_raw", "data.list[].currency_icon"),
            ParserFieldSpec("listing_start_time_raw", "data.list[].listing_start_time"),
            ParserFieldSpec("available_quantity", "data.list[].available_quantity"),
            ParserFieldSpec("wfs_available_quantity", "data.list[].wfs_available_quantity"),
            ParserFieldSpec("average_rating", "data.list[].average_rating"),
            ParserFieldSpec("review_count", "data.list[].review_count"),
            ParserFieldSpec("gtin", "data.list[].gtin"),
            ParserFieldSpec("upc", "data.list[].upc"),
            ParserFieldSpec("brand", "data.list[].brand"),
            ParserFieldSpec("status_name", "data.list[].status_name"),
            ParserFieldSpec("fulfillment_type", "data.list[].fulfillment_type"),
            ParserFieldSpec("fulfillment_type_name", "data.list[].fulfillment_type_name"),
            ParserFieldSpec("item_url", "data.list[].item_url"),
            ParserFieldSpec("variant_unique_id", "data.list[].variant_unique_id"),
        ),
        skip_rules=(
            "item_id is required for listing identity",
            "store_id is required for store-level metrics",
            "price without a currency code must be marked currency_status=missing",
        ),
    ),
    "sale_stat_page_list": DataPagesParserSpec(
        parser_key="sale_stat_page_list",
        api_path="/basicOpen/platformStatisticsV2/saleStat/pageList",
        record_path="data[]",
        target_table="fact_walmart_sales_item_daily",
        unique_key_candidates=(
            ("business_date_la", "source_account_ref", "store_id", "item_id", "result_type"),
            ("business_date_la", "source_account_ref", "source_group_key", "result_type"),
        ),
        fields=(
            ParserFieldSpec("date_collect", "data[].date_collect", required=True),
            ParserFieldSpec("currency_code", "data[].currency_code"),
            ParserFieldSpec("platform_code", "data[].platform_code"),
            ParserFieldSpec("platform_name", "data[].platform_name"),
            ParserFieldSpec("item_id_candidates", "data[].platform_product_id"),
            ParserFieldSpec("platform_product_title", "data[].platform_product_title"),
            ParserFieldSpec("store_id", "data[].sid"),
            ParserFieldSpec("store_name", "data[].store_name"),
            ParserFieldSpec("msku", "data[].msku"),
            ParserFieldSpec("local_sku", "data[].sku"),
            ParserFieldSpec("product_name", "data[].product_name"),
            ParserFieldSpec("volume_total", "data[].volumeTotal"),
        ),
        skip_rules=(
            "result_type must come from request metadata, not from response inference",
            "date_collect must be expanded by date and volumeTotal must not be double counted",
            "platform_product_id arrays with more than one value require source_group_key and allocation_status=needs_owner_decision",
        ),
    ),
    "order_v2_list": DataPagesParserSpec(
        parser_key="order_v2_list",
        api_path="/pb/mp/order/v2/list",
        record_path="data.list[].item_info[]",
        target_table="fact_walmart_order_items",
        unique_key_candidates=(
            ("source_account_ref", "global_order_no", "global_item_no"),
            ("source_account_ref", "global_order_no", "order_item_no"),
            ("source_account_ref", "global_order_no", "item_info_id"),
            ("source_account_ref", "global_order_no", "source_line_hash"),
        ),
        fields=(
            ParserFieldSpec("global_order_no", "data.list[].global_order_no", required=True),
            ParserFieldSpec("global_purchase_time_raw", "data.list[].global_purchase_time"),
            ParserFieldSpec("raw_status", "data.list[].status"),
            ParserFieldSpec("raw_status_sub", "data.list[].status_sub"),
            ParserFieldSpec("flow_node", "data.list[].flow_node"),
            ParserFieldSpec("store_id", "data.list[].store_id"),
            ParserFieldSpec("amount_currency_code", "data.list[].amount_currency"),
            ParserFieldSpec("order_total_amount", "data.list[].transaction_info[].order_total_amount"),
            ParserFieldSpec("global_item_no", "data.list[].item_info[].global_item_no"),
            ParserFieldSpec("order_item_no", "data.list[].item_info[].order_item_no"),
            ParserFieldSpec("item_info_id", "data.list[].item_info[].id"),
            ParserFieldSpec("quantity", "data.list[].item_info[].quantity"),
            ParserFieldSpec("msku", "data.list[].item_info[].msku"),
            ParserFieldSpec("local_sku", "data.list[].item_info[].local_sku"),
            ParserFieldSpec("product_no", "data.list[].item_info[].product_no"),
            ParserFieldSpec("platform_order_no", "data.list[].item_info[].platform_order_no"),
            ParserFieldSpec("sales_revenue_amount", "data.list[].item_info[].sales_revenue_amount"),
            ParserFieldSpec("discount_amount", "data.list[].item_info[].discount_amount"),
        ),
        skip_rules=(
            "global_order_no is required",
            "line identity must use the first stable candidate present in the response",
            "global_purchase_time is interpreted as China time before converting to UTC and America/Los_Angeles business date",
        ),
        warnings=(
            "sample order detection uses zero sales revenue, zero order total, or discount offset rules",
        ),
    ),
    "walmart_return_order_list": DataPagesParserSpec(
        parser_key="walmart_return_order_list",
        api_path="/basicOpen/openapi/multiplatform/walmart/returnOrder/list",
        record_path="data.list[].items[]",
        target_table="fact_walmart_refund_items",
        unique_key_candidates=(
            (
                "source_account_ref",
                "return_order_id",
                "purchase_order_id",
                "msku_or_local_sku",
                "tracking_no",
                "status_time",
            ),
            ("source_account_ref", "return_order_id", "source_line_hash"),
        ),
        fields=(
            ParserFieldSpec("return_order_id", "data.list[].returnOrderId", required=True),
            ParserFieldSpec("return_type", "data.list[].returnType", required=True),
            ParserFieldSpec("return_type_name", "data.list[].returnTypeName"),
            ParserFieldSpec("return_order_date_raw", "data.list[].returnOrderDate"),
            ParserFieldSpec("return_by_date_raw", "data.list[].returnByDate"),
            ParserFieldSpec("customer_order_id", "data.list[].customerOrderId"),
            ParserFieldSpec("store_id", "data.list[].storeId"),
            ParserFieldSpec("store_name", "data.list[].storeName"),
            ParserFieldSpec("site_code", "data.list[].siteCode"),
            ParserFieldSpec("purchase_order_id", "data.list[].items[].purchaseOrderId"),
            ParserFieldSpec("msku", "data.list[].items[].msku"),
            ParserFieldSpec("local_sku", "data.list[].items[].localSku"),
            ParserFieldSpec("quantity", "data.list[].items[].quantityDisplay"),
            ParserFieldSpec("refund_amount", "data.list[].items[].lineTotalAmount"),
            ParserFieldSpec("refund_currency_code", "data.list[].items[].lineTotalCurrency"),
            ParserFieldSpec("item_status", "data.list[].items[].status"),
            ParserFieldSpec("current_refund_status", "data.list[].items[].currentRefundStatus"),
            ParserFieldSpec("status_time_raw", "data.list[].items[].statusTime"),
            ParserFieldSpec("tracking_no", "data.list[].items[].trackingNo"),
        ),
        skip_rules=(
            "returnType must equal REFUND",
            "return_order_id is required",
            "return_line_id is not documented and must not be invented",
        ),
        warnings=(
            "store returnOrderDate as refund business time and retain item statusTime for state lineage",
        ),
    ),
    "walmart_advertiser_list": DataPagesParserSpec(
        parser_key="walmart_advertiser_list",
        api_path="/basicOpen/adReport/advertiser/list",
        record_path="data.list[]",
        target_table="dim_walmart_advertisers",
        unique_key_candidates=(("source_account_ref", "advertiser_id"),),
        fields=(
            ParserFieldSpec("advertiser_id", "data.list[].advertiserId", required=True),
            ParserFieldSpec("advertiser_name", "data.list[].advertiserName"),
            ParserFieldSpec("raw_status", "data.list[].status"),
        ),
        skip_rules=("advertiser_id is required before querying SP ad item reports",),
    ),
    "walmart_ad_item_sp_list": DataPagesParserSpec(
        parser_key="walmart_ad_item_sp_list",
        api_path="/basicOpen/multiplatform/ads/reportAdItemSpList",
        record_path="data.list[]",
        target_table="fact_walmart_ad_item_sp_daily",
        unique_key_candidates=(
            (
                "business_date_la",
                "source_account_ref",
                "advertiser_id",
                "campaign_id",
                "ad_group_id",
                "ad_item_id",
                "item_id",
            ),
            ("business_date_la", "source_account_ref", "advertiser_id", "key"),
            ("business_date_la", "source_account_ref", "advertiser_id", "source_line_hash"),
        ),
        fields=(
            ParserFieldSpec("advertiser_id", "data.list[].advertiserId", required=True),
            ParserFieldSpec("ad_spend_amount", "data.list[].adSpend"),
            ParserFieldSpec("item_id", "data.list[].itemId"),
            ParserFieldSpec("campaign_id", "data.list[].campaignId"),
            ParserFieldSpec("ad_group_id", "data.list[].adGroupId"),
            ParserFieldSpec("ad_item_id", "data.list[].adItemId"),
            ParserFieldSpec("ad_name", "data.list[].adName"),
            ParserFieldSpec("campaign_name", "data.list[].campaignName"),
            ParserFieldSpec("ad_group_name", "data.list[].adGroupName"),
            ParserFieldSpec("mp_advertiser_name", "data.list[].mpAdvertiserName"),
            ParserFieldSpec("mp_seller_name", "data.list[].mpSellerName"),
            ParserFieldSpec("attributed_sales_amount", "data.list[].attributedSales"),
            ParserFieldSpec("attributed_orders", "data.list[].attributedOrders"),
            ParserFieldSpec("attributed_units", "data.list[].attributedUnits"),
            ParserFieldSpec("advertised_sku_sales_amount", "data.list[].advertisedSkuSales"),
            ParserFieldSpec("advertised_sku_units", "data.list[].advertisedSkuUnits"),
            ParserFieldSpec("num_ads_clicks", "data.list[].numAdsClicks"),
            ParserFieldSpec("num_ads_shown", "data.list[].numAdsShown"),
            ParserFieldSpec("acos", "data.list[].acos"),
            ParserFieldSpec("roas", "data.list[].roas"),
            ParserFieldSpec("cpc", "data.list[].cpc"),
            ParserFieldSpec("ctr", "data.list[].ctr"),
            ParserFieldSpec("cvr", "data.list[].cvr"),
            ParserFieldSpec("key", "data.list[].key"),
        ),
        skip_rules=(
            "advertiser_id is required and must come from advertiser/list",
            "ad item reports are joined to DATA-PAGES MARTs by itemId after date-level aggregation",
        ),
    ),
}


def get_data_pages_parser_spec(parser_key: DataPagesParserKey) -> DataPagesParserSpec:
    return DATA_PAGES_PARSER_SPECS[parser_key]
