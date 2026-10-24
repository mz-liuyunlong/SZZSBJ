"""Read contract for the domestic-warehouse batch board.

One row is one current receipt line. Days in warehouse use the Taipei calendar date.
Outbound events stay unknown until an outbound allocation table is published.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

type MappingStatus = Literal["unresolved", "matched"]
type ArrivalDateStatus = Literal["known", "unknown"]
type BatchSort = Literal["received_date_desc", "received_date_asc", "qty_desc"]
type OutboundStatus = Literal["unknown"]
type OutboundReason = Literal["source_not_published"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


class BatchFilterQuery(StrictSchema):
    warehouse_id: list[str] = Field(default_factory=list, max_length=50)
    store_id: list[str] = Field(default_factory=list, max_length=50)
    owner_uid: list[Annotated[str, Field(min_length=1, max_length=255, pattern=r"\S")]] = Field(
        default_factory=list, max_length=50, description="当前产品负责人UID；多值OR"
    )
    sku: list[str] = Field(default_factory=list, max_length=50)
    purchase_order_sn: list[str] = Field(default_factory=list, max_length=50)
    receipt_order_sn: list[str] = Field(default_factory=list, max_length=50)
    mapping_status: MappingStatus | None = None
    received_from: date | None = None
    received_to: date | None = None
    search: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _range(self) -> BatchFilterQuery:
        if (
            self.received_from is not None
            and self.received_to is not None
            and self.received_from > self.received_to
        ):
            raise ValueError("received_from must be on or before received_to")
        if self.search is not None and not self.search.strip():
            self.search = None
        return self


class BatchListQuery(BatchFilterQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort: BatchSort = "received_date_desc"


class DomesticFilterOption(StrictSchema):
    value: str = Field(description="稳定店铺ID或当前产品负责人UID，不使用名称作身份")
    label: str = Field(description="展示名称；未知或歧义时使用ID")


class DomesticFilterOptionsData(StrictSchema):
    stores: list[DomesticFilterOption]
    owners: list[DomesticFilterOption]


class BatchLinkRead(StrictSchema):
    id: UUID
    batch_order_sn: str | None
    batch_no: str | None
    store_id: str | None
    mapped_qty: int | None
    mapping_status: MappingStatus
    mapping_method: str | None


class BatchRowRead(StrictSchema):
    id: UUID
    source_account_ref: str
    receipt_order_sn: str
    line_ordinal: int
    purchase_order_sn: str | None
    source_warehouse_id: str | None
    sku: str | None
    received_qty: int | None
    receive_time: str | None
    received_business_date: date | None
    days_in_warehouse: int | None
    arrival_date_status: ArrivalDateStatus
    mapping_status: MappingStatus
    links: list[BatchLinkRead]


class BatchListData(StrictSchema):
    items: list[BatchRowRead]
    total: int


class BatchSummaryData(StrictSchema):
    receipt_batch_count: int = Field(description="当前筛选下的收货行数")
    received_qty: int = Field(description="实收数量合计，空数量不计入")
    warehouse_count: int = Field(description="有仓库 ID 的收货行，按仓库去重")
    matched_batch_count: int = Field(description="至少有一条已对应库存批次的收货行")
    unresolved_batch_count: int = Field(description="还没有已对应库存批次的收货行")
    missing_arrival_date_count: int = Field(description="收货日为空，在仓天数未知")
    as_of: date


class OutboundTrace(StrictSchema):
    status: OutboundStatus = "unknown"
    reason: OutboundReason = "source_not_published"
    events: list[str] = Field(default_factory=list)


class BatchTraceData(StrictSchema):
    batch: BatchRowRead
    outbound: OutboundTrace


class DomesticReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    freshness_at: datetime | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
