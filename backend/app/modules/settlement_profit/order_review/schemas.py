"""订单审核接口的请求 / 响应模型（PRP §7）。金额一律字符串小数 + 币种。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReviewStage = Literal["first", "final"]
ReviewDecision = Literal["pass", "reject", "revert"]
SortOrder = Literal["asc", "desc"]


class Money(BaseModel):
    amount: str
    currency_code: str


def money(value: Decimal | None, currency: str) -> Money | None:
    return None if value is None else Money(amount=f"{value:.4f}", currency_code=currency)


class PeriodRead(BaseModel):
    store_id: str
    store_name: str | None
    period_key: str
    report_date: date
    period_start_date: date | None
    period_end_date: date | None
    bill_month: date | None
    line_count: int
    pending_count: int
    auto_count: int
    first_passed_count: int
    final_passed_count: int
    rejected_count: int
    calc_version: int | None
    calculated_at: datetime | None


class PeriodListData(BaseModel):
    items: list[PeriodRead]


class CostSourceRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    quantity: str | None = None
    msku: str | None = None
    scope_ref: str | None = None
    purchase_cny: str | None = None
    head_cny: str | None = None
    last_leg_cny: str | None = None
    reasons: list[str] = Field(default_factory=list)
    entry_id: str | None = None


class LineRead(BaseModel):
    id: UUID
    review_id: UUID
    store_id: str
    period_key: str
    bill_month: date
    line_key: str
    line_kind: str
    fulfillment_type: str
    platform_order_no: str
    order_line_no: str
    gtin: str | None
    item_id: str | None
    sku: str | None
    msku: str | None
    owner_id: str | None
    posted_date: date | None
    quantity: str
    transaction_types: list[str]
    sales: Money
    refund: Money
    promotion: Money
    commission: Money
    return_fee: Money
    tax_withheld: Money
    wfs_fulfillment_fee: Money
    mcf_fee: Money
    settlement_amount: Money
    purchase: Money | None
    head: Money | None
    last_leg: Money | None
    cost_total: Money | None
    cost_total_usd: Money | None
    profit_usd: Money | None
    fx_rate: str | None
    fx_status: str
    cost_sources: list[CostSourceRead]
    cost_entry_ids: list[str]
    reasons: list[str]
    auto_passed: bool
    review_status: str
    review_reasons: list[str] = Field(default_factory=list)
    first_reviewed_by: str | None
    first_reviewed_at: datetime | None
    final_reviewed_by: str | None
    final_reviewed_at: datetime | None
    version: int
    calc_version: int


class LineListMeta(BaseModel):
    source: str = "finance_settlement_profit_v3"
    source_tables: list[str] = Field(
        default_factory=lambda: ["fact_settlement_order_lines", "mart_settlement_order_review"]
    )
    total: int
    page: int
    page_size: int


class LineListData(BaseModel):
    items: list[LineRead]


class LookupData(BaseModel):
    kind: str
    items: list[str]
    truncated: bool


class TransactionTypeRead(BaseModel):
    code: str
    name_zh: str | None
    name_en: str
    category: str
    translated: bool


class TransactionTypeListData(BaseModel):
    items: list[TransactionTypeRead]


class CostEntryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    msku: str = Field(min_length=1, max_length=320)
    shipping_list_code: str | None = Field(default=None, max_length=64)
    outbound_order_no: str | None = Field(default=None, max_length=64)

    @field_validator("msku", "shipping_list_code", "outbound_order_no")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def scope_ref(self) -> str:
        if self.shipping_list_code:
            return f"shipping:{self.shipping_list_code}"
        if self.outbound_order_no:
            return f"outbound:{self.outbound_order_no}"
        raise ValueError("scope requires shipping_list_code or outbound_order_no")


class CostEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: str = Field(pattern=r"^[0-9]{1,32}$")
    scope: CostEntryScope
    entry_kind: Literal["confirm", "override"]
    purchase_cny: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    head_cny: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    last_leg_cny: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    reason: str | None = Field(default=None, max_length=2000)


class CostEntryRead(BaseModel):
    id: UUID
    store_id: str
    msku: str
    scope_ref: str
    shipping_list_code: str | None
    outbound_order_no: str | None
    entry_kind: str
    purchase_cny: str | None
    head_cny: str | None
    last_leg_cny: str | None
    reason: str | None
    status: str
    version: int
    actor_id: str
    created_at: datetime


class CostEntryResult(BaseModel):
    entry: CostEntryRead
    affected_lines: int
    recalculated_periods: int
    replayed: bool = False


class CostEntryRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=1)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_ids: list[UUID] = Field(min_length=1, max_length=500)
    stage: ReviewStage
    decision: ReviewDecision
    comment: str | None = Field(default=None, max_length=2000)
    # ≥ 20 行时必填（PRP §5），值固定为 CONFIRM_BATCH_REVIEW，前端二次确认后带上
    confirm_token: str | None = Field(default=None, max_length=64)


class ReviewLineResult(BaseModel):
    review_id: UUID
    line_key: str
    ok: bool
    review_status: str
    version: int
    error_code: str | None = None
    message: str | None = None


class ReviewResultData(BaseModel):
    items: list[ReviewLineResult]
    succeeded: int
    failed: int


class RecalcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_ids: list[str] = Field(default_factory=list, max_length=50)
    period_keys: list[str] = Field(default_factory=list, max_length=200)
    report_date_from: date | None = None


class RecalcPeriodResult(BaseModel):
    store_id: str
    period_key: str
    status: str
    lines_total: int
    lines_new_version: int
    lines_unchanged: int
    lines_retired: int
    auto_passed: int
    pending: int
    calc_version: int


class RecalcResultData(BaseModel):
    items: list[RecalcPeriodResult]
    periods_total: int
