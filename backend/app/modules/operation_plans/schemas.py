from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

PeriodType = Literal["month", "quarter"]
ConflictPolicy = Literal["skip_existing", "overwrite_existing"]
ImportStatus = Literal["success", "updated", "skipped", "failed"]
BatchStatus = Literal["completed", "partial_completed", "failed"]
OperationStatus = Literal["normal", "new_product", "clearance"]
PlanStatus = Literal["normal", "lagging", "severe_lagging", "unplanned", "clearance"]
StockStatus = Literal["normal", "risk"]
SearchField = Literal["item_id", "sku", "msku", "product_name"]
OperationPlanSortField = Literal["sales_completion_rate", "gross_profit_completion_rate"]
OperationPlanSortOrder = Literal["asc", "desc"]


class OperationPlanMeta(BaseModel):
    source_objects: list[str] = Field(default_factory=list)
    period_type: PeriodType
    period_key: str
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class OperationPlanSummary(BaseModel):
    sales_target_amount: Decimal = Decimal("0")
    sales_actual_amount: Decimal = Decimal("0")
    sales_forecast_amount: Decimal = Decimal("0")
    gross_profit_target_amount: Decimal = Decimal("0")
    gross_profit_actual_amount: Decimal = Decimal("0")
    gross_profit_forecast_amount: Decimal = Decimal("0")
    product_count: int = 0
    unplanned_count: int = 0
    lagging_count: int = 0
    severe_lagging_count: int = 0
    adjusted_product_count: int = 0
    sales_target_adjust_amount: Decimal = Decimal("0")
    gross_profit_target_adjust_amount: Decimal = Decimal("0")
    clearance_count: int = 0
    period_label: str
    period_progress_rate: Decimal = Decimal("0")


class OperationPlanOwnerRow(BaseModel):
    owner_ref: str | None = None
    owner_name: str
    product_count: int
    sales_target_amount: Decimal
    sales_actual_amount: Decimal = Decimal("0")
    sales_actual_qty: Decimal = Decimal("0")
    sales_completion_rate: Decimal = Decimal("0")
    gross_profit_target_amount: Decimal
    gross_profit_actual_amount: Decimal = Decimal("0")
    gross_profit_completion_rate: Decimal = Decimal("0")
    lagging_count: int = 0
    severe_lagging_count: int = 0
    stock_risk_count: int = 0


class OperationPlanSummaryData(BaseModel):
    summary: OperationPlanSummary
    owners: list[OperationPlanOwnerRow]


class OperationPlanProductQuery(BaseModel):
    period_type: PeriodType = "month"
    period_key: str
    owner_ref: str | None = None
    store_id: str | None = None
    operation_status: OperationStatus | None = None
    plan_status: PlanStatus | None = None
    stock_status: StockStatus | None = None
    sort_field: OperationPlanSortField | None = None
    sort_order: OperationPlanSortOrder = "desc"
    search_field: SearchField = "item_id"
    keyword: str | None = None
    batch_values: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

    @field_validator("batch_values", mode="before")
    @classmethod
    def parse_batch_values(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split("\n") if item.strip()]


class OperationPlanProductRow(BaseModel):
    plan_id: UUID
    item_id: str
    product_name: str | None = None
    sku: str | None = None
    msku: str
    owner_ref: str | None = None
    owner_name: str | None = None
    store_id: str | None = None
    store_name: str | None = None
    store_count: int = 0
    msku_count: int = 0
    sku_count: int = 0
    last_sales_amount: Decimal = Decimal("0")
    last_gross_profit_amount: Decimal = Decimal("0")
    last_gross_profit_rate: Decimal = Decimal("0")
    sales_target_amount: Decimal
    sales_actual_amount: Decimal = Decimal("0")
    sales_actual_qty: Decimal = Decimal("0")
    sales_completion_rate: Decimal = Decimal("0")
    sales_forecast_amount: Decimal = Decimal("0")
    gross_profit_target_amount: Decimal
    gross_profit_actual_amount: Decimal = Decimal("0")
    gross_profit_completion_rate: Decimal = Decimal("0")
    gross_profit_forecast_amount: Decimal = Decimal("0")
    wfs_available_qty: Decimal = Decimal("0")
    inbound_qty: Decimal = Decimal("0")
    arriving_qty: Decimal = Decimal("0")
    inventory_support_rate: Decimal = Decimal("0")
    operation_status: OperationStatus
    plan_status: PlanStatus
    stock_status: StockStatus
    adjusted: bool = False
    event_count: int = 0
    remark: str | None = None


class OperationPlanProductListData(BaseModel):
    items: list[OperationPlanProductRow]
    total: int
    page: int
    page_size: int


class SelectOption(BaseModel):
    label: str
    value: str
    count: int | None = None


class OperationPlanOptionsData(BaseModel):
    owners: list[SelectOption]
    stores: list[SelectOption]
    operation_statuses: list[SelectOption]
    plan_statuses: list[SelectOption]
    stock_statuses: list[SelectOption]


class OperationPlanImportRowResult(BaseModel):
    row_number: int
    item_id: str | None = None
    msku: str | None = None
    sales_target_amount: Decimal | None = None
    gross_profit_target_amount: Decimal | None = None
    remark: str | None = None
    import_status: ImportStatus
    error_message: str | None = None
    suggestion: str | None = None


class OperationPlanImportData(BaseModel):
    batch_id: UUID
    status: BatchStatus
    row_count: int
    success_count: int
    failed_count: int
    warning_count: int
    existing_count: int
    created_plan_count: int
    updated_plan_count: int
    skipped_count: int
    rows: list[OperationPlanImportRowResult]


class OperationPlanTargetUpdateRequest(BaseModel):
    sales_target_amount: Decimal = Field(gt=0)
    gross_profit_target_amount: Decimal
    reason: str | None = None

    @field_validator("gross_profit_target_amount")
    @classmethod
    def gross_profit_not_too_large(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        sales = info.data.get("sales_target_amount")
        if sales is not None and value > sales:
            raise ValueError("gross_profit_target_amount cannot exceed sales_target_amount")
        return value


class OperationPlanClearanceRequest(BaseModel):
    reason: str | None = None


class OperationPlanEventRow(BaseModel):
    event_id: UUID
    event_type: str
    event_label: str
    sales_target_amount: Decimal | None = None
    gross_profit_target_amount: Decimal | None = None
    reason: str | None = None
    actor_name: str
    created_at: datetime


class OperationPlanEventListData(BaseModel):
    items: list[OperationPlanEventRow]


class OperationPlanPeriodInfo(BaseModel):
    period_type: PeriodType
    period_key: str
    period_start_date: date
    period_end_date: date
