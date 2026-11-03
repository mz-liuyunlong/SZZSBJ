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
ArrivalBucket = Literal["overdue", "d15", "d30", "d60", "d60_plus", "none"]
EtaSource = Literal["real", "plan", "region"]

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
    owner: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=16)
    arrival_bucket: ArrivalBucket | None = None
    only_exceptions: bool = False
    only_external: bool = False


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


class ShipmentItemLine(Strict):
    """8088 货件产品明细: per item shipped / received / put away / normal / abnormal."""

    msku: str
    sku: str
    product_name: str
    gtin: str
    item_id: str | None = None
    owners: list[str] = Field(default_factory=list)
    declared_units: int
    shipped_units: int
    lingxing_received_units: int
    walmart_received_units: int | None = None
    put_away_units: int | None = None
    damaged_units: int
    normal_units: int
    over_units: int
    abnormal_units: int | None = None
    abnormal: bool


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
    # 8088 derived view (computed when read; rule version WFS-RULES-20261010)
    owners: list[str] = Field(default_factory=list)
    region: str | None = None
    its_inferred: bool = False
    baseline_units: int | None = None
    baseline_from: Literal["SP", "declare"] | None = None
    diff_units: int | None = None
    boxes: int | None = None
    eta: date | None = None
    eta_source: EtaSource | None = None
    eta_source_label: str | None = None
    eta_passed_days: int | None = None
    sellable_date: date | None = None
    sellable_real: bool = False
    arrival_bucket: ArrivalBucket | None = None
    shipped_out: bool = False
    carrier_delivered_at: str | None = None
    walmart_signed_date: date | None = None
    walmart_first_receipt: date | None = None
    walmart_last_receipt: date | None = None
    walmart_receiving: bool = False
    walmart_done: bool = False
    d0: date | None = None
    d0_real: bool = False
    days_since_d0: int | None = None
    external: bool = False
    age_days: int | None = None
    exception_types: list[str] = Field(default_factory=list)


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
    by_arrival_bucket: dict[str, int] = Field(default_factory=dict)
    with_exceptions: int = 0
    external: int = 0
    rule_version: str = ""
    rule_date: date | None = None
    freshness: BoardFreshness


class StoreOption(Strict):
    value: str
    label: str


class ShipmentBoardOptions(Strict):
    stores: list[StoreOption]
    owners: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    arrival_buckets: list[StoreOption] = Field(default_factory=list)


class ShipmentException(Strict):
    type: str
    rule_family: str
    severity: Literal["high", "mid", "low"]
    found: date | None = None
    description: str
    source: Literal["real", "calc", "demo"]
    qty: int | None = None


class ShipmentBoardDetail(ShipmentBoardRow):
    goods: list[ShipmentGoodsLine] = Field(default_factory=list)
    items: list[ShipmentItemLine] = Field(default_factory=list)
    exceptions: list[ShipmentException] = Field(default_factory=list)
    shipping_lists: list[dict[str, Any]] = Field(default_factory=list)
    distribution_addresses: str | None = None
    return_addresses: str | None = None
    creator: str | None = None
    country_name: str | None = None
    return_address: dict | None = None
    expected_delivery_at: datetime | str | None = None
    allocation: dict | None = None
    lingxing_note: str | None = None


class ProductShipmentLine(Strict):
    shipment_id: str
    status_name: str
    msku: str
    shipped_units: int
    signed_units: int
    shelved_units: int
    eta: date | None = None
    eta_source: EtaSource | None = None
    sellable_date: date | None = None
    sellable_real: bool = False
    bucket: str
    region: str | None = None


class ProductBoardRow(Strict):
    """8088 产品维度: store × Item ID, shipped-not-sellable units by sellable-date bucket."""

    id: str
    store_id: str
    store_name: str | None = None
    item_id: str
    mskus: list[str]
    skus: list[str]
    product_name: str | None = None
    shipments: int
    in_transit_units: int
    buckets: dict[str, int]
    signed_not_put_units: int
    arrived_shipped_units: int
    arrived_signed_units: int
    arrived_shelved_units: int
    receiving_gap_units: int
    signed_zero_shelved: int
    next_eta: date | None = None
    next_sellable: date | None = None
    lines: list[ProductShipmentLine] = Field(default_factory=list)


class ProductBoardList(Strict):
    items: list[ProductBoardRow]
    total: int
    data_asof: datetime
    freshness: BoardFreshness
