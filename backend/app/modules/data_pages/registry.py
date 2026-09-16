from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DataPageKey = Literal["daily_sales", "order_profit", "listing_management"]


@dataclass(frozen=True, slots=True)
class DataPageRegistryEntry:
    """Stable implementation registry for DATA-PAGES read-model API acceptance."""

    key: DataPageKey
    task_ref: str
    route_path: str
    permission: str
    mart_object: str
    frontend_page: str
    frontend_api_adapter: str
    empty_data_behavior: str
    fallback_behavior: str
    current_boundary: str
    quality_checks: tuple[str, ...]


DATA_PAGE_API_REGISTRY: Final[dict[DataPageKey, DataPageRegistryEntry]] = {
    "daily_sales": DataPageRegistryEntry(
        key="daily_sales",
        task_ref="DATA-PAGES-1D",
        route_path="/api/sales/daily-sales",
        permission="sales:daily-sales:read",
        mart_object="mart_daily_sales_item_day",
        frontend_page="frontend/src/pages/sales/DailySalesPage.tsx",
        frontend_api_adapter="frontend/src/pages/sales/dailySalesApi.ts",
        empty_data_behavior="Return a successful envelope with data.items=[] and meta.total=0.",
        fallback_behavior="Frontend keeps local acceptance rows when the backend request fails while MART sync is not implemented.",
        current_boundary="Read-only MART API; no Lingxing call, parser writer, backfill, Celery task, production migration, or production database operation.",
        quality_checks=(
            "business_date_la is a Walmart business date in America/Los_Angeles.",
            "source_account_ref is constrained by the caller's integration source-account scope.",
            "meta.source_objects contains only mart_daily_sales_item_day.",
            "cost_status and missing_cost_codes are surfaced for incomplete cost inputs.",
            "money fields are serialized as strings from Decimal-compatible values.",
        ),
    ),
    "order_profit": DataPageRegistryEntry(
        key="order_profit",
        task_ref="DATA-PAGES-1E",
        route_path="/api/sales/order-profit",
        permission="sales:daily-sales:read",
        mart_object="mart_order_profit_sku_day",
        frontend_page="frontend/src/pages/sales/OrderProfitPage.tsx",
        frontend_api_adapter="frontend/src/pages/sales/orderProfitApi.ts",
        empty_data_behavior="Return a successful envelope with data.items=[] and meta.total=0.",
        fallback_behavior="Frontend keeps local acceptance rows when the backend request fails while MART sync is not implemented.",
        current_boundary="Read-only MART API; no Lingxing call, parser writer, backfill, Celery task, production migration, or production database operation.",
        quality_checks=(
            "business_date_la is a Walmart business date in America/Los_Angeles.",
            "source_account_ref is constrained by the caller's integration source-account scope.",
            "meta.source_objects contains only mart_order_profit_sku_day.",
            "store_ids_json and item_ids_json remain display-safe string lists.",
            "cost_status and missing_cost_codes are surfaced for incomplete profit inputs.",
        ),
    ),
    "listing_management": DataPageRegistryEntry(
        key="listing_management",
        task_ref="DATA-PAGES-1F",
        route_path="/api/listings/walmart",
        permission="products:read",
        mart_object="mart_listing_management_current",
        frontend_page="frontend/src/pages/products/ListingManagementPage.tsx",
        frontend_api_adapter="frontend/src/pages/products/listingManagementApi.ts",
        empty_data_behavior="Return a successful envelope with data.items=[] and meta.total=0.",
        fallback_behavior="Frontend keeps local acceptance rows when the backend request fails while MART sync is not implemented.",
        current_boundary="Read-only MART API; no Lingxing call, parser writer, backfill, Celery task, production migration, or production database operation.",
        quality_checks=(
            "source_account_ref is constrained by the caller's integration source-account scope.",
            "meta.source_objects contains only mart_listing_management_current.",
            "listing rows expose display-safe fields only and do not expose RAW payloads.",
            "tags are normalized to string lists for frontend rendering.",
            "latest_calculated_at reflects MART calculation freshness when rows exist.",
        ),
    ),
}


def registry_source_objects(key: DataPageKey) -> list[str]:
    return [DATA_PAGE_API_REGISTRY[key].mart_object]
