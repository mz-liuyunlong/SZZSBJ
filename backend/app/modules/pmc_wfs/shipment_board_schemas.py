"""Read-only shipment board contracts; Lingxing fulfillment is explicitly absent in M1."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.modules.pmc_domestic.warehouse_schemas import Strict

LabelState = Literal["PENDING", "READY", "FAILED"]
LingxingSync = Literal["PENDING"]
SortField = Literal["created_at"]
SortDir = Literal["asc", "desc"]
KeywordField = Literal["shipment", "pk", "msku", "sku", "item", "gtin"]


class ShipmentBoardFilter(Strict):
    store_id: str | None = Field(default=None, max_length=64)
    keyword: str = Field(default="", max_length=200)
    keyword_field: KeywordField = "shipment"
    only_test: bool = False


class ShipmentBoardQuery(ShipmentBoardFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort_by: SortField = "created_at"
    sort_dir: SortDir = "desc"


class ShipmentBoardRow(Strict):
    id: str
    shipment_id: str
    operation_id: UUID
    ticket_id: UUID
    ticket_number: int
    order_id: UUID
    pk: str
    store_id: str
    store_name: str | None = None
    sku: str | None = None
    product_name: str | None = None
    item_id: str | None = None
    gtin: str | None = None
    msku: str | None = None
    business_test: bool
    its: bool
    label_state: LabelState
    creation_state: str
    ticket_state: str
    lingxing_sync_status: LingxingSync = "PENDING"
    declared_units: int | None = None
    shipped_units: int | None = None
    received_units: int | None = None
    created_at: datetime


class ShipmentBoardList(Strict):
    items: list[ShipmentBoardRow]
    total: int
    data_asof: datetime


class ShipmentBoardSummary(Strict):
    total: int
    pending_lingxing_sync: int
    test: int


class StoreOption(Strict):
    value: str
    label: str


class ShipmentBoardOptions(Strict):
    stores: list[StoreOption]


class ShipmentBoardDetail(ShipmentBoardRow):
    return_address: dict | None = None
    expected_delivery_at: datetime | str | None = None
    allocation: dict | None = None
    lingxing_note: str = "领星履约数据尚未接入；发货/到仓/入库字段未取得。"
