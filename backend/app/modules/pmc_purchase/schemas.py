"""Request / response schemas for the PMC purchase board read API (Gate 3, G3-E).

Every response is wrapped in the project envelope (``SuccessEnvelope``); money is
serialized as a plain decimal string; dates are Beijing calendar dates (rules §3.2).
Field names follow PRP §7.1–7.4 and the Demo v1.4 columns.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

Money = Annotated[
    Decimal,
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
]

type StatusFilter = Literal["s2", "s3", "s4", "overdue", "s9", "s0", "unattributed"]
type SearchType = Literal["sku", "item_id", "gtin", "msku", "order_sn"]
type ItemIdSourceFilter = Literal[
    "from_system_plan",
    "from_plan_remark",
    "from_packing_slip",
    "pending_packing_slip",
    "unresolved",
]
type BoardSort = Literal[
    "order_date_desc",
    "order_date_asc",
    "overdue_days_desc",
    "arrival_date_desc",
    "amount_desc",
]
type OverdueKind = Literal["purchase", "arrival"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


# --- queries ---------------------------------------------------------------------------------


class BoardFilterQuery(StrictSchema):
    """Filters shared by the board list and the summary cards (PRP §7.1 / §7.2)."""

    owner_uid: list[str] = Field(default_factory=list, max_length=50)
    store_id: list[str] = Field(default_factory=list, max_length=50)
    status: list[StatusFilter] = Field(default_factory=list, max_length=7)
    search_type: SearchType | None = None
    search_values: list[str] = Field(default_factory=list, max_length=200)
    item_id_source: list[ItemIdSourceFilter] = Field(default_factory=list, max_length=5)
    order_date_from: date | None = None
    order_date_to: date | None = None
    qty_min: int | None = Field(default=None, ge=0)
    qty_max: int | None = Field(default=None, ge=0)
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    wfs_not_ready: bool | None = None
    today_followup: bool = False

    @model_validator(mode="after")
    def _ranges(self) -> BoardFilterQuery:
        if self.search_values and self.search_type is None:
            raise ValueError("search_type is required when search_values are given")
        if (
            self.order_date_from
            and self.order_date_to
            and self.order_date_from > self.order_date_to
        ):
            raise ValueError("order_date_from must not be after order_date_to")
        if self.qty_min is not None and self.qty_max is not None and self.qty_min > self.qty_max:
            raise ValueError("qty_min must not exceed qty_max")
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must not exceed price_max")
        return self

    def normalized_search_values(self) -> list[str]:
        seen: dict[str, None] = {}
        for raw in self.search_values:
            for piece in raw.replace(",", " ").replace("\n", " ").split():
                seen.setdefault(piece.strip(), None)
        return [v for v in seen if v]


class BoardListQuery(BoardFilterQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort: BoardSort = "order_date_desc"


class SkuCycleQuery(StrictSchema):
    sku: list[str] = Field(min_length=1, max_length=100)


class PendingPlanQuery(StrictSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    store_id: list[str] = Field(default_factory=list, max_length=50)
    overdue_only: bool = False
    search_values: list[str] = Field(default_factory=list, max_length=200)


# --- shared fragments --------------------------------------------------------------------------


class StoreRef(StrictSchema):
    id: str | None
    name: str | None
    attributed: bool


class OwnerRef(StrictSchema):
    uid: str | None
    name: str | None


class ItemIdRef(StrictSchema):
    item_id: str | None
    source: ItemIdSourceFilter
    source_ref: str | None
    matched_at: datetime | None
    match_status: Literal["matched", "pending", "unresolved"]
    msku: str | None
    gtin: str | None
    fulfillment_type: str | None
    wfs_not_ready: bool | None


class StageRef(StrictSchema):
    stage_code: Literal["S1", "S2", "S3", "S4", "S9", "S0", "UNKNOWN"]
    stage_start: date | None
    stage_start_estimated: bool
    threshold_days: int | None
    due_date: date | None
    overdue_days: int
    overdue_kind: OverdueKind | None
    alert_due_since: date | None


class SkuCycleBrief(StrictSchema):
    value_days: Money | None
    source: Literal["samples", "baseline_mix", "lingxing_default", "no_baseline"] | None
    sample_count: int | None
    unstable: bool


class SkuCycleSample(StrictSchema):
    purchase_order_sn: str
    order_date: date
    arrival_date: date
    cycle_days: int
    used: bool
    exclusion: Literal["auto_short", "manual", "before_baseline", "outside_window"] | None


# --- board list (7.1) ---------------------------------------------------------------------


class BoardRowRead(StrictSchema):
    purchase_order_sn: str
    order_item_id: str
    plan_sn: str | None
    plan_sns: list[str]
    order_status: int | None
    stage: StageRef
    store: StoreRef
    sku: str | None
    product_name: str | None
    item_id: ItemIdRef
    owner: OwnerRef
    quantity_total: int | None
    quantity_allocated: int
    quantity_received: int
    progress_ratio: Money | None
    remaining_quantity: int
    order_date: date | None
    order_create_date: date | None
    plan_create_date: date | None
    arrival_date: date | None
    arrival_receipt_order_sn: str | None
    purchase_cycle_days: int | None
    approval_cycle_days: int | None
    sku_cycle: SkuCycleBrief
    unit_price: Money | None
    amount_allocated: Money | None
    amount_total: Money | None
    currency_code: str | None
    calculated_at: datetime


class BoardListData(StrictSchema):
    items: list[BoardRowRead]
    total: int


# --- summary (7.2) ---------------------------------------------------------------------------


class MoneyByCurrency(StrictSchema):
    currency_code: str | None
    amount: Money


class BoardSummaryData(StrictSchema):
    awaiting_arrival_orders: int = Field(description="S3+S4 采购单数（去重单号）")
    arrival_overdue_orders: int = Field(description="S3/S4 且 overdue_days>0 采购单数")
    purchase_overdue_orders: int = Field(description="采购单待下单（S2）逾期数")
    purchase_overdue_plans: int = Field(description="计划待采购（status=2 未转单）逾期数")
    average_purchase_cycle_days_90d: Money | None = Field(
        description="近 90 天到仓采购单 purchase_cycle_days 平均"
    )
    month_purchase_amount: list[MoneyByCurrency] = Field(
        description="本月下单 amount_allocated 合计，按币种"
    )
    unstable_sku_count: int
    itemid_pending_lines: int
    wfs_not_ready_lines: int
    unattributed_store_lines: int
    as_of: date


# --- order detail (7.3) ---------------------------------------------------------------------


class OrderReceiptRef(StrictSchema):
    receipt_order_sn: str
    is_arrival_receipt: bool


class OrderPlanRef(StrictSchema):
    plan_sn: str
    plan_status: int | None
    plan_create_date: date | None
    quantity_plan: int | None
    remark_item_id: str | None
    store_id: str | None


class OrderDetailData(StrictSchema):
    purchase_order_sn: str
    order_status: int | None
    order_date: date | None
    order_create_date: date | None
    quantity_total: int | None
    quantity_received: int
    progress_ratio: Money | None
    arrival_date: date | None
    amount_total: Money | None
    currency_code: str | None
    stage: StageRef
    lines: list[BoardRowRead]
    receipts: list[OrderReceiptRef]
    plans: list[OrderPlanRef]
    sku_cycles: list[SkuCycleRead]


# --- SKU cycles (7.4) ------------------------------------------------------------------------


class SkuCycleRead(StrictSchema):
    sku: str
    value_days: Money | None
    source: Literal["samples", "baseline_mix", "lingxing_default", "no_baseline"]
    sample_count: int
    baseline_days: int | None
    baseline_set_on: date | None
    lingxing_default_days: int | None
    unstable: bool
    range_days: int | None
    samples: list[SkuCycleSample]
    rule_version: int
    calculated_at: datetime


class SkuCycleListData(StrictSchema):
    items: list[SkuCycleRead]
    missing: list[str] = Field(description="requested SKUs without a DWS row")


# --- pending plans (S2 card drill-down) ------------------------------------------------------


class PendingPlanRead(StrictSchema):
    plan_sn: str
    plan_status: int | None
    plan_create_date: date | None
    pending_since: date | None
    pending_since_estimated: bool
    pending_days: int | None
    overdue_days: int
    store: StoreRef
    sku: str | None
    product_name: str | None
    quantity_plan: int | None
    remark_item_id: str | None


class PendingPlanListData(StrictSchema):
    items: list[PendingPlanRead]
    total: int
    threshold_days: int


# --- meta ----------------------------------------------------------------------------------------


class PurchaseReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    freshness_at: datetime | None = None
    rule_version: int | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


# --- manual cycle overrides (7.5, G3-F) --------------------------------------------------------

type OverrideKind = Literal["exclude", "restore", "arrival_date", "baseline"]


class CycleOverrideRequest(StrictSchema):
    """One human correction to a SKU purchase cycle (rules §4.2; append-only)."""

    source_account_ref: str = Field(min_length=1, max_length=128)
    kind: OverrideKind
    purchase_order_sn: str | None = Field(default=None, min_length=1, max_length=64)
    value_days: int | None = Field(default=None, ge=0, le=365)
    value_date: date | None = None
    reason: str = Field(min_length=1, max_length=1000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _shape(self) -> CycleOverrideRequest:
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        if self.source_account_ref != self.source_account_ref.strip():
            raise ValueError("source_account_ref must be canonical")
        if self.kind in ("exclude", "restore"):
            if not self.purchase_order_sn:
                raise ValueError("purchase_order_sn is required for exclude / restore")
            if self.value_days is not None or self.value_date is not None:
                raise ValueError("exclude / restore take no value")
        elif self.kind == "arrival_date":
            if not self.purchase_order_sn or self.value_date is None:
                raise ValueError("arrival_date requires purchase_order_sn and value_date")
            if self.value_days is not None:
                raise ValueError("arrival_date takes value_date only")
        else:  # baseline
            if self.value_days is None:
                raise ValueError("baseline requires value_days")
            if self.purchase_order_sn is not None or self.value_date is not None:
                raise ValueError("baseline applies to the whole SKU")
        return self


class CycleOverrideRead(StrictSchema):
    id: UUID
    source_account_ref: str
    sku: str
    kind: OverrideKind
    purchase_order_sn: str | None
    value_days: int | None
    value_date: date | None
    before: dict[str, object]
    after: dict[str, object]
    reason: str
    operator_ref: str
    request_id: str | None
    effective_from: datetime
    effective_to: datetime | None
    is_active: bool
    created_at: datetime


class CycleOverrideMutationData(StrictSchema):
    override: CycleOverrideRead
    replaced_override_id: UUID | None = Field(
        description="previous active baseline closed by this record (baseline only)"
    )
    idempotent_replay: bool = Field(description="true when the request_id was already applied")
    sku_cycle: SkuCycleRead | None = Field(description="SKU cycle after the refresh")
    refresh_board_rows: int


class CycleOverrideListData(StrictSchema):
    sku: str
    items: list[CycleOverrideRead]


OrderDetailData.model_rebuild()
