"""WFS 费用明细接口模型。金额用字符串（4 位小数），我方视角：正 = Walmart 付我们，负 = 扣费。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WfsFeeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: str
    fee_source: str
    fee_type: str
    reason_code: str
    detail: str
    source_ref: str
    transaction_date: date
    date_charged: date
    period_start: date | None
    period_end: date | None
    report_key: str | None
    report_date: date | None
    bill_match: str
    po_number: str
    partner_id: str
    gtin: str
    item_id: str
    msku: str
    local_sku: str
    quantity: str | None
    amount_usd: str
    original_amount: str | None
    discount_savings: str | None
    attribution: str
    allocation_basis: str
    parent_line_id: UUID | None
    missing_since: datetime | None
    raw_file_id: UUID
    adjusted: bool = False
    children: list[WfsFeeLineRead] = Field(default_factory=list)


class WfsFeeLineListData(BaseModel):
    items: list[WfsFeeLineRead]
    total: int
    page: int
    page_size: int


class WfsFeeSummaryRow(BaseModel):
    store_id: str
    report_key: str | None
    report_date: date | None
    fee_type: str
    rows: int
    amount_usd: str


class WfsFeeSummaryData(BaseModel):
    items: list[WfsFeeSummaryRow]
    total_amount_usd: str


class WfsFeeCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: str
    report_key: str
    fee_type: str
    report_date: date | None
    lingxing_amount: str | None
    lingxing_rows: int
    report_amount: str | None
    report_rows: int
    status: str
    verified_reason: str | None
    verified_by: str | None
    verified_at: datetime | None
    refreshed_at: datetime


class WfsFeeCheckListData(BaseModel):
    items: list[WfsFeeCheckRead]


class WfsFeeFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: str
    fee_source: str
    origin: str
    file_name: str
    period_start: date | None
    period_end: date | None
    declared_total: str | None
    row_count: int
    rows_new: int
    rows_duplicate: int
    status: str
    reject_reason: str | None
    actor: str
    created_at: datetime


class WfsFeeFileListData(BaseModel):
    items: list[WfsFeeFileRead]


class WfsFeeImportData(BaseModel):
    file_id: UUID
    file_name: str
    store_id: str
    fee_source: str
    period_start: date | None
    period_end: date | None
    status: str
    rows_parsed: int
    rows_new: int
    rows_duplicate: int
    duplicate_of_file: bool
    reject_reason: str | None
    warnings: list[str]


class WfsFeeAdjustRequest(BaseModel):
    kind: Literal["realloc", "company"]
    reason: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class WfsFeeVerifyRequest(BaseModel):
    store_id: str = Field(pattern=r"^[0-9]+$")
    report_key: str = Field(min_length=1, max_length=64)
    fee_type: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class WfsFeeTypeRead(BaseModel):
    code: str
    name: str
    source: str


class WfsFeePeriodRead(BaseModel):
    """店铺 × 沃尔玛账单期（来自领星账单），给页面做店铺 / 账单期筛选。

    店铺代码 = 店铺名横杠前的编号。
    """

    store_id: str
    store_code: str
    store_name: str | None
    report_key: str | None
    report_date: date | None
    period_start_date: date | None
    period_end_date: date | None


class WfsFeePeriodListData(BaseModel):
    items: list[WfsFeePeriodRead]