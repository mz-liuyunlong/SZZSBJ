from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
CaseStatus = Literal["未开Case", "已开Case", "跟进中", "已追回", "驳回", "已关闭"]
Priority = Literal["高", "中", "低"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class WfsFeeAlertQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    store_id: Nonblank | None = None
    owner_ref: Nonblank | None = None
    status: CaseStatus | None = None
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class WfsFeeAlertRead(StrictSchema):
    id: str
    business_date_la: date
    store_id: str
    store_name: str | None
    owner_ref: str | None
    item_id: str
    msku: str
    local_sku: str | None
    product_name: str | None
    order_count: Decimal
    sales_qty: Decimal
    cost_quantity: Decimal
    expected_fee_amount: Decimal | None
    actual_fee_amount: Decimal | None
    variance_amount: Decimal | None
    variance_rate: Decimal | None
    expected_unit_amount: Decimal | None
    actual_unit_amount: Decimal | None
    status: CaseStatus
    case_no: str | None
    reason: str | None
    priority: Priority
    claim_amount: Decimal | None
    recovered_amount: Decimal
    pending_recovery_amount: Decimal
    case_opened_at: datetime | None
    next_follow_at: date | None
    latest_follow: str | None


class WfsFeeAlertListData(StrictSchema):
    items: list[WfsFeeAlertRead]


class WfsFeeAlertMeta(StrictSchema):
    page: int
    page_size: int
    total: int


class WfsFeeActualWrite(StrictSchema):
    source_account_ref: Nonblank
    business_date_la: date
    store_id: Nonblank
    item_id: Nonblank
    msku: Nonblank
    source_line_ref: Nonblank
    actual_fee_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    currency_code: Literal["USD"] = "USD"
    source_type: Nonblank = "walmart_statement"
    source_observed_at: datetime | None = None


class WfsFeeActualWriteResult(StrictSchema):
    source_line_ref: str
    mart_updated: bool


class WfsFeeCaseWrite(StrictSchema):
    status: CaseStatus
    case_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    priority: Priority = "中"
    claim_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    recovered_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    case_opened_at: datetime | None = None
    next_follow_at: date | None = None
    latest_follow: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
