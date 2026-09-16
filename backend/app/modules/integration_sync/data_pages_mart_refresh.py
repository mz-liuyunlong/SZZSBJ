from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from app.modules.data_pages.registry import DATA_PAGE_API_REGISTRY, DataPageKey

RefreshMode = Literal["delete_insert"]
RefreshGranularity = Literal["business_date_item", "business_date_sku", "current_listing"]


class DataPagesMartRefreshPlanError(RuntimeError):
    """Safe MART refresh planning error without account or row-level details."""


@dataclass(frozen=True, slots=True)
class DataPagesMartRefreshSpec:
    """Refresh contract for one DATA-PAGES MART object.

    The spec is metadata-only. A future authorized runner may use it to execute a
    delete-insert refresh, but this module does not run SQL or connect to production.
    """

    key: DataPageKey
    mart_table: str
    refresh_mode: RefreshMode
    granularity: RefreshGranularity
    source_tables: tuple[str, ...]
    requires_business_date_window: bool
    boundary_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataPagesMartRefreshPlan:
    key: DataPageKey
    mart_table: str
    refresh_mode: RefreshMode
    source_account_ref: str
    business_date_from: date | None
    business_date_to: date | None
    source_tables: tuple[str, ...]


DATA_PAGES_MART_REFRESH_SPECS: Final[dict[DataPageKey, DataPagesMartRefreshSpec]] = {
    "daily_sales": DataPagesMartRefreshSpec(
        key="daily_sales",
        mart_table="mart_daily_sales_item_day",
        refresh_mode="delete_insert",
        granularity="business_date_item",
        source_tables=(
            "dim_lingxing_stores",
            "dim_walmart_listings",
            "dim_walmart_advertisers",
            "fact_walmart_sales_item_daily",
            "fact_walmart_order_items",
            "fact_walmart_refund_items",
            "fact_walmart_ad_item_sp_daily",
        ),
        requires_business_date_window=True,
        boundary_notes=(
            "Refresh by Walmart business date in America/Los_Angeles.",
            "Ad spend is aggregated by date, store, and item before joining the MART.",
            "Cost fields remain nullable until Product Management cost sources are connected.",
        ),
    ),
    "order_profit": DataPagesMartRefreshSpec(
        key="order_profit",
        mart_table="mart_order_profit_sku_day",
        refresh_mode="delete_insert",
        granularity="business_date_sku",
        source_tables=(
            "mart_daily_sales_item_day",
            "fact_walmart_order_items",
            "fact_walmart_refund_items",
            "fact_walmart_ad_item_sp_daily",
        ),
        requires_business_date_window=True,
        boundary_notes=(
            "Order profit is derived from daily sales facts and order/refund/ad facts.",
            "The refresh must keep SKU aggregation deterministic across stores and items.",
        ),
    ),
    "listing_management": DataPagesMartRefreshSpec(
        key="listing_management",
        mart_table="mart_listing_management_current",
        refresh_mode="delete_insert",
        granularity="current_listing",
        source_tables=(
            "dim_lingxing_stores",
            "dim_walmart_listings",
            "fact_walmart_sales_item_daily",
            "fact_walmart_ad_item_sp_daily",
        ),
        requires_business_date_window=False,
        boundary_notes=(
            "Listing management refreshes the current listing snapshot.",
            "Rolling 7/14/30 day metrics are derived from sales and ad facts.",
        ),
    ),
}


def mart_refresh_keys() -> frozenset[DataPageKey]:
    return frozenset(DATA_PAGES_MART_REFRESH_SPECS)


def mart_refresh_spec_for(key: DataPageKey) -> DataPagesMartRefreshSpec:
    return DATA_PAGES_MART_REFRESH_SPECS[key]


def build_mart_refresh_plan(
    key: DataPageKey,
    *,
    source_account_ref: str,
    business_date_from: date | None = None,
    business_date_to: date | None = None,
) -> DataPagesMartRefreshPlan:
    source_account_ref = _validate_source_account_ref(source_account_ref)
    spec = mart_refresh_spec_for(key)
    _validate_registry_alignment(spec)
    if spec.requires_business_date_window and (
        business_date_from is None or business_date_to is None
    ):
        raise DataPagesMartRefreshPlanError("DATA_PAGES_MART_REFRESH_WINDOW_REQUIRED")
    if business_date_from is not None and business_date_to is not None:
        if business_date_to < business_date_from:
            raise DataPagesMartRefreshPlanError("DATA_PAGES_MART_REFRESH_WINDOW_INVALID")
    return DataPagesMartRefreshPlan(
        key=spec.key,
        mart_table=spec.mart_table,
        refresh_mode=spec.refresh_mode,
        source_account_ref=source_account_ref,
        business_date_from=business_date_from,
        business_date_to=business_date_to,
        source_tables=spec.source_tables,
    )


def _validate_source_account_ref(value: str) -> str:
    if not value or value != value.strip() or len(value) > 128:
        raise DataPagesMartRefreshPlanError("DATA_PAGES_MART_REFRESH_SOURCE_ACCOUNT_REF_INVALID")
    return value


def _validate_registry_alignment(spec: DataPagesMartRefreshSpec) -> None:
    registry_entry = DATA_PAGE_API_REGISTRY[spec.key]
    if registry_entry.mart_object != spec.mart_table:
        raise DataPagesMartRefreshPlanError("DATA_PAGES_MART_REFRESH_REGISTRY_MISMATCH")
