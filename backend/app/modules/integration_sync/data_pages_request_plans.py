from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint
from app.modules.integration_sync.data_pages_catalog import (
    DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY,
    DataPagesSyncInterfaceSpec,
)
from app.modules.integration_sync.parsers.lingxing_data_pages import DataPagesParserKey

PaginationStyle = Literal["offset", "page", "page_num"]
DateWindowKind = Literal["none", "date", "datetime"]
StaticBodyValue = str | int | bool | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataPagesRequestPlanSpec:
    """Safe request-planning contract for one DATA-PAGES source interface.

    These specs describe how a future controlled runner may build requests. They do not
    execute Lingxing calls, read credentials, persist RAW responses, or enable schedules.
    """

    parser_key: DataPagesParserKey
    endpoint_path: LingxingEndpoint
    pagination_style: PaginationStyle
    page_size_field: str
    page_field: str | None = None
    offset_field: str | None = None
    date_window_kind: DateWindowKind = "none"
    start_field: str | None = None
    end_field: str | None = None
    store_scope_field: str | None = None
    static_body_fields: tuple[tuple[str, StaticBodyValue], ...] = ()
    fanout_field: str | None = None
    fanout_values: tuple[int | str, ...] = ()
    dependency_parser_key: DataPagesParserKey | None = None
    runtime_required_fields: tuple[str, ...] = ()
    boundary_notes: tuple[str, ...] = ()

    def static_body_dict(self) -> dict[str, StaticBodyValue]:
        return dict(self.static_body_fields)


DATA_PAGES_REQUEST_PLAN_SPECS: Final[tuple[DataPagesRequestPlanSpec, ...]] = (
    DataPagesRequestPlanSpec(
        parser_key="seller_list_multi_platform",
        endpoint_path="/pb/mp/shop/v2/getSellerList",
        pagination_style="offset",
        offset_field="offset",
        page_size_field="length",
        runtime_required_fields=("platform_code",),
        boundary_notes=(
            "Store metadata is captured before store-scoped Walmart joins are planned.",
        ),
    ),
    DataPagesRequestPlanSpec(
        parser_key="walmart_listing_list",
        endpoint_path="/basicOpen/multiplatform/walmart/list",
        pagination_style="offset",
        offset_field="offset",
        page_size_field="length",
        boundary_notes=(
            "The first implementation intentionally does not add a store request filter.",
        ),
    ),
    DataPagesRequestPlanSpec(
        parser_key="sale_stat_page_list",
        endpoint_path="/basicOpen/platformStatisticsV2/saleStat/pageList",
        pagination_style="page",
        page_field="page",
        page_size_field="length",
        date_window_kind="date",
        start_field="start_date",
        end_field="end_date",
        store_scope_field="sids",
        static_body_fields=(("data_type", 1),),
        fanout_field="result_type",
        fanout_values=(1, 2, 3),
        boundary_notes=(
            "result_type is planned explicitly for sales, order count, and sales amount.",
        ),
    ),
    DataPagesRequestPlanSpec(
        parser_key="order_v2_list",
        endpoint_path="/pb/mp/order/v2/list",
        pagination_style="offset",
        offset_field="offset",
        page_size_field="length",
        date_window_kind="datetime",
        start_field="start_time",
        end_field="end_time",
        store_scope_field="store_id",
        static_body_fields=(("date_type", "global_purchase_time"),),
        boundary_notes=(
            "The order window is based on global_purchase_time for profit lineage.",
        ),
    ),
    DataPagesRequestPlanSpec(
        parser_key="walmart_return_order_list",
        endpoint_path="/basicOpen/openapi/multiplatform/walmart/returnOrder/list",
        pagination_style="page_num",
        page_field="pageNum",
        page_size_field="pageSize",
        date_window_kind="date",
        start_field="startDate",
        end_field="endDate",
        store_scope_field="storeIdList",
        static_body_fields=(("dateType", "1"), ("returnTypeList", ("REFUND",))),
        boundary_notes=("Only REFUND return records are planned for DATA-PAGES marts.",),
    ),
    DataPagesRequestPlanSpec(
        parser_key="walmart_advertiser_list",
        endpoint_path="/basicOpen/adReport/advertiser/list",
        pagination_style="page",
        page_field="page",
        page_size_field="limit",
        static_body_fields=(("paging", True),),
        boundary_notes=(
            "Advertiser IDs are collected before Walmart SP ad item reports are planned.",
        ),
    ),
    DataPagesRequestPlanSpec(
        parser_key="walmart_ad_item_sp_list",
        endpoint_path="/basicOpen/multiplatform/ads/reportAdItemSpList",
        pagination_style="page_num",
        page_field="pageNum",
        page_size_field="pageSize",
        date_window_kind="date",
        start_field="startDate",
        end_field="endDate",
        static_body_fields=(("paging", True),),
        dependency_parser_key="walmart_advertiser_list",
        runtime_required_fields=("advertiserIds", "campaignType"),
        boundary_notes=(
            "advertiserIds must come from advertiser/list before ad item requests run.",
        ),
    ),
)

DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY: Final = {
    spec.parser_key: spec for spec in DATA_PAGES_REQUEST_PLAN_SPECS
}


def data_pages_request_plan_parser_keys() -> frozenset[DataPagesParserKey]:
    return frozenset(DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY)


def request_plan_for(parser_key: DataPagesParserKey) -> DataPagesRequestPlanSpec:
    return DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY[parser_key]


def sync_interface_for_request_plan(
    parser_key: DataPagesParserKey,
) -> DataPagesSyncInterfaceSpec:
    return DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
