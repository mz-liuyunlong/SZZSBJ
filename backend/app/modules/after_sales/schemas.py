from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CsvText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
KeywordText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=256)]
SearchField = Literal["sku", "msku", "item_id", "product_name", "order_id"]
RiskLevel = Literal["pending"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class RefundBaseQuery(StrictSchema):
    start_date: date
    end_date: date
    store_id: CsvText = ""
    owner_ref: CsvText = ""
    reason: CsvText = ""
    responsibility: CsvText = ""
    search_field: SearchField = "sku"
    keyword: KeywordText = ""
    batch_values: CsvText = ""
    # Opaque exact identity for store_id + item_id + MSKU drill-down.
    product_key: KeywordText = ""

    @model_validator(mode="after")
    def validate_range(self) -> RefundBaseQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("date range must not exceed 367 days")
        return self


class RefundProductAnalysisQuery(RefundBaseQuery):
    selected_product_key: KeywordText = ""
    limit: int = Field(default=20, ge=1, le=100)


class RefundItemQuery(RefundBaseQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    sort_by: Literal[
        "refund_time",
        "purchase_time",
        "refund_qty",
        "refund_amount",
        "refund_loss",
    ] = "refund_time"
    sort_order: Literal["asc", "desc"] = "desc"


class FilterOption(StrictSchema):
    value: str
    label: str
    color: str | None = None


class RefundFacets(StrictSchema):
    stores: list[FilterOption]
    owners: list[FilterOption]
    reasons: list[FilterOption]
    responsibilities: list[FilterOption]


class RefundSummary(StrictSchema):
    refund_orders: int
    refund_item_rows: int
    refund_qty: Decimal
    refund_amount: Decimal
    refund_currency_code: str | None
    refund_loss_amount: Decimal
    sales_qty: Decimal
    refund_rate: Decimal | None
    avg_refund_amount_per_unit: Decimal | None
    avg_refund_loss_per_unit: Decimal | None


class RefundComparison(StrictSchema):
    previous_start_date: date
    previous_end_date: date
    refund_orders_change_rate: Decimal | None
    refund_qty_change_rate: Decimal | None
    refund_loss_change_rate: Decimal | None
    refund_rate_change_pp: Decimal | None


class RefundTrendPoint(StrictSchema):
    date: date
    refund_orders: int
    refund_qty: Decimal
    refund_amount: Decimal
    refund_loss_amount: Decimal
    sales_qty: Decimal
    refund_rate: Decimal | None


class RefundReasonTag(StrictSchema):
    code: str
    name: str
    category_code: str
    category_name: str
    color: str


class RefundResponsibilityTag(StrictSchema):
    code: str
    name: str
    color: str
    source: str
    confidence: str
    editable: bool = True


class RefundReasonRead(RefundReasonTag):
    refund_orders: int
    refund_qty: Decimal
    refund_amount: Decimal
    refund_loss_amount: Decimal


class RefundResponsibilityRead(StrictSchema):
    code: str
    name: str
    color: str
    refund_orders: int
    refund_qty: Decimal
    refund_amount: Decimal
    refund_loss_amount: Decimal


class RefundOverviewData(StrictSchema):
    summary: RefundSummary
    comparison: RefundComparison
    trend: list[RefundTrendPoint]
    reasons: list[RefundReasonRead]
    responsibilities: list[RefundResponsibilityRead]
    facets: RefundFacets


class RefundReadMeta(StrictSchema):
    source_objects: list[str]
    start_date: date
    end_date: date
    latest_updated_at: datetime | None


class RefundProductRead(StrictSchema):
    product_key: str
    store_id: str
    store_name: str | None
    local_sku: str | None
    msku: str | None
    item_id: str | None
    product_name: str | None
    owner_ref: str | None
    refund_orders: int
    refund_qty: Decimal
    refund_amount: Decimal
    refund_loss_amount: Decimal
    sales_qty: Decimal
    refund_rate: Decimal | None
    top_reason: RefundReasonTag | None
    top_responsibility: RefundResponsibilityTag | None
    risk_level: RiskLevel = "pending"


class RefundProductTrendPoint(StrictSchema):
    date: date
    refund_qty: Decimal
    refund_orders: int
    refund_amount: Decimal
    refund_loss_amount: Decimal
    sales_qty: Decimal
    refund_rate: Decimal | None


class RefundHeatRow(StrictSchema):
    product_key: str
    values: list[Decimal]


class RefundLagBucket(StrictSchema):
    key: Literal["0_3", "4_7", "8_14", "15_30", "31_plus"]
    refund_orders: int
    refund_qty: Decimal
    ratio: Decimal | None
    refund_amount: Decimal
    refund_loss_amount: Decimal


class RefundLagAnalysis(StrictSchema):
    average_days: Decimal | None
    median_days: Decimal | None
    main_bucket: Literal["0_3", "4_7", "8_14", "15_30", "31_plus"] | None
    main_bucket_ratio: Decimal | None
    eligible_item_rows: int
    missing_time_rows: int
    buckets: list[RefundLagBucket]


class RefundProductDetail(RefundProductRead):
    trend: list[RefundProductTrendPoint]
    reasons: list[RefundReasonRead]
    lag: RefundLagAnalysis


class RefundProductAnalysisData(StrictSchema):
    dates: list[date]
    items: list[RefundProductRead]
    heat: list[RefundHeatRow]
    selected: RefundProductDetail | None


class RefundItemRead(StrictSchema):
    id: str
    store_id: str
    store_name: str | None
    owner_ref: str | None
    item_id: str | None
    product_name: str | None
    local_sku: str | None
    msku: str | None
    return_order_id: str
    customer_order_id: str | None
    purchase_order_id: str | None
    platform_order_id: str
    purchase_time_at: datetime | None
    refund_time_at: datetime | None
    refund_lag_days: Decimal | None
    return_qty: Decimal
    refund_amount: Decimal | None
    refund_currency_code: str | None
    refund_loss_amount: Decimal | None
    return_reason_code: str | None
    return_description: str | None
    reason: RefundReasonTag
    responsibility: RefundResponsibilityTag
    current_refund_status: str | None
    refund_completed: bool


class RefundItemListData(StrictSchema):
    items: list[RefundItemRead]


class RefundItemListMeta(RefundReadMeta):
    page: int
    page_size: int
    total: int
