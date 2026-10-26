"""New inbound contract; deliberately distinct from receipt-line /batches."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InboundFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_id: list[str] = Field(default_factory=list, max_length=50)
    store_id: list[str] = Field(default_factory=list, max_length=50)
    owner_uid: list[str] = Field(
        default_factory=list, max_length=50, description="当前产品负责人UID；多值OR"
    )
    sku: list[str] = Field(default_factory=list, max_length=50)
    inbound_order_sn: list[str] = Field(default_factory=list, max_length=50)
    purchase_order_sn: list[str] = Field(default_factory=list, max_length=50)
    inbound_from: date | None = None
    inbound_to: date | None = None
    inventory_status: Literal["known", "unknown"] | None = None
    search: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_filters(self) -> InboundFilter:
        if self.inbound_from and self.inbound_to and self.inbound_from > self.inbound_to:
            raise ValueError("invalid date range")
        for name in (
            "warehouse_id",
            "store_id",
            "owner_uid",
            "sku",
            "inbound_order_sn",
            "purchase_order_sn",
        ):
            if any(not v.strip() or len(v) > 255 for v in getattr(self, name)):
                raise ValueError("invalid source identity")
        return self


class InboundOptionsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_id: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_warehouses(self) -> InboundOptionsQuery:
        InboundFilter(warehouse_id=self.warehouse_id)
        return self


class InboundOption(BaseModel):
    value: str
    label: str


class InboundStatusOption(InboundOption):
    disabled: bool = True
    reason: str


class InboundOptions(BaseModel):
    stores: list[InboundOption]
    owners: list[InboundOption]
    statuses: list[InboundStatusOption]
    owner_basis: Literal["current_product_owner"] = "current_product_owner"


class InboundQuery(InboundFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort: Literal["inbound_date_desc", "inbound_date_asc", "balance_desc"] = "inbound_date_desc"


class ItemIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    gtin: str | None = None


class InboundRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    publication_id: UUID
    source_account_ref: str
    source_warehouse_id: str
    warehouse_name: str | None
    inbound_order_sn: str
    sku: str
    product_name: str
    store_id: str | None
    store_name: str | None
    attribution_status: Literal["known", "unknown"]
    purchase_order_sns: list[str]
    draft_nos: list[str] = Field(default_factory=list)
    item_identities: list[ItemIdentity] = Field(default_factory=list)
    identity_status: Literal["resolved", "missing", "partial", "conflict"] = "missing"
    inbound_at_raw: str | None
    inbound_at: datetime | None
    arrival_business_date: date | None
    arrival_source: Literal["inventory_statement", "batch_fallback", "unknown"]
    arrival_date_status: Literal["known", "unknown"]
    days_in_warehouse: int | None
    total_inbound_qty: int | None
    parent_inbound_qty: int | None = Field(description="IB×SKU层级数量，跨店铺行不可重复相加")
    quantity_scope: Literal["inbound_sku", "unknown"]
    balance_num: int | None
    inventory_status: Literal["known", "unknown"]
    batch_nos: list[str]
    batch_details: list[dict[str, Any]]
    history_complete: bool
    source_kind: Literal["inventory_statement", "batch_backfill"]


class InboundList(BaseModel):
    items: list[InboundRow]
    total: int


class InboundSummary(BaseModel):
    board_row_count: int
    inbound_order_count: int
    sku_count: int
    balance_qty: int
    unknown_inventory_row_count: int
    total_inbound_qty: int
    unknown_inbound_qty_count: int
    missing_arrival_date_count: int
    as_of: date


class InboundTrace(BaseModel):
    batch: InboundRow
    inbound_events: list[dict[str, Any]]
    outbound_status: Literal["unknown"] = "unknown"
    outbound_reason: Literal["source_not_published"] = "source_not_published"


class InboundMeta(BaseModel):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str] = Field(
        default_factory=lambda: [
            "mart_domestic_inbound_batch_board",
            "gov_domestic_board_publications",
        ]
    )
    data_status: Literal["not_published", "ready"]
    freshness_at: datetime | None = None
    publication_ids: list[UUID] = Field(default_factory=list)
    coverage_start: date | None = None
    coverage_end: date | None = None
    as_of: date
    available_capabilities: list[str] = Field(
        default_factory=lambda: [
            "procurement_inbound",
            "batch_stock",
            "inbound_trace",
        ]
    )
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
