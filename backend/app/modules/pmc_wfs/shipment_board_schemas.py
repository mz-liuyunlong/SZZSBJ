"""Read-only shipment board contracts (M2: Lingxing-fed board + creation linkage)."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.modules.pmc_domestic.warehouse_schemas import Strict

LabelState = Literal["PENDING", "READY", "FAILED"]
LingxingSync = Literal["SYNCED", "PENDING"]
RowSource = Literal["lingxing", "creation_only"]
SortField = Literal["created_at", "updated_at"]
SortDir = Literal["asc", "desc"]
KeywordField = Literal["shipment", "inbound", "pk", "msku", "sku", "item", "gtin", "shipping"]

# Lingxing cargo status (0–4) → Chinese board label.
STATUS_LABELS: dict[int, str] = {
    0: "待发货",
    1: "在途",
    2: "收货中",
    3: "已关闭",
    4: "已取消",
}


class ShipmentBoardFilter(Strict):
    store_id: str | None = Field(default=None, max_length=64)
    keyword: str = Field(default="", max_length=200)
    keyword_field: KeywordField = "shipment"
    only_test: bool = False
    status: int | None = Field(default=None, ge=0, le=4)
    sync: LingxingSync | None = None


class ShipmentBoardQuery(ShipmentBoardFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort_by: SortField = "created_at"
    sort_dir: SortDir = "desc"


class ShipmentGoodsLine(Strict):
    msku: str | None = None
    sku: str | None = None
    product_name: str | None = None
    gtin: str | None = None
    declare_num: int | None = None
    shipments_num: int | None = None
    received_num: int | None = None
    damaged_qty: int | None = None


class ShipmentBoardRow(Strict):
    id: str
    source: RowSource
    shipment_id: str
    inbound_order_id: str | None = None
    store_id: str
    store_name: str | None = None
    status: int | None = None
    status_name: str | None = None
    status_label: str
    cargo_sync_status: str | None = None
    lingxing_sync_status: LingxingSync
    business_test: bool
    its: bool | None = None
    pk: str | None = None
    sku: str | None = None
    product_name: str | None = None
    item_id: str | None = None
    gtin: str | None = None
    msku: str | None = None
    sku_count: int = 0
    declared_units: int | None = None
    shipped_units: int | None = None
    received_units: int | None = None
    damaged_units: int | None = None
    logistics_code: str | None = None
    shipping_codes: list[str] = Field(default_factory=list)
    shipping_status: str | None = None
    warehouse_id: str | None = None
    actual_delivery_date: date | None = None
    arrival_date: date | None = None
    expected_arrival_date: date | None = None
    logistics_numbers: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    to_await_at: datetime | None = None
    to_receive_at: datetime | None = None
    to_closed_at: datetime | None = None
    to_cancelled_at: datetime | None = None
    operation_id: UUID | None = None
    ticket_id: UUID | None = None
    ticket_number: int | None = None
    order_id: UUID | None = None
    label_state: LabelState | None = None
    creation_state: str | None = None
    ticket_state: str | None = None


class BoardFreshness(Strict):
    publication_id: UUID | None = None
    source_observed_at: datetime | None = None
    published_at: datetime | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    stale: bool = True


class ShipmentBoardList(Strict):
    items: list[ShipmentBoardRow]
    total: int
    data_asof: datetime
    freshness: BoardFreshness


class ShipmentBoardSummary(Strict):
    total: int
    by_status: dict[str, int]
    pending_lingxing_sync: int
    test: int
    received_short: int
    freshness: BoardFreshness


class StoreOption(Strict):
    value: str
    label: str


class ShipmentBoardOptions(Strict):
    stores: list[StoreOption]


class ShipmentBoardDetail(ShipmentBoardRow):
    goods: list[ShipmentGoodsLine] = Field(default_factory=list)
    shipping_lists: list[dict[str, Any]] = Field(default_factory=list)
    distribution_addresses: str | None = None
    return_addresses: str | None = None
    creator: str | None = None
    country_name: str | None = None
    return_address: dict | None = None
    expected_delivery_at: datetime | str | None = None
    allocation: dict | None = None
    lingxing_note: str | None = None


class ProductBoardRow(Strict):
    id: str
    store_id: str
    store_name: str | None = None
    msku: str | None = None
    sku: str | None = None
    product_name: str | None = None
    gtin: str | None = None
    shipments: int
    declared_units: int | None = None
    shipped_units: int | None = None
    received_units: int | None = None
    damaged_units: int | None = None
    in_transit_units: int | None = None


class ProductBoardList(Strict):
    items: list[ProductBoardRow]
    total: int
    data_asof: datetime
    freshness: BoardFreshness
