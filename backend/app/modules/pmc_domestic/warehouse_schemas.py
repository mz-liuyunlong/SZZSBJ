"""Warehouse contracts keep stock, approval quantity and physical packing distinct."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)


Dimension = Annotated[Decimal, Field(ge=1, le=300, max_digits=12, decimal_places=4)]
Weight = Annotated[Decimal, Field(ge=Decimal("0.01"), le=200, max_digits=12, decimal_places=4)]
NOTE_LABELS = {
    "arrival_incomplete": "到货不齐",
    "labels": "等标签",
    "materials": "等包材",
    "operations": "等运营确认",
    "schedule": "仓库排期",
    "quality": "质检问题",
    "other": "其他",
    "resolved": "已处理",
}


class WarehouseFilter(Strict):
    exception: Literal["overpack"] | None = None
    store_id: str | None = Field(default=None, max_length=64)
    status: Literal["todo", "packed", "all"] = "todo"
    keyword: str = Field(default="", max_length=200)
    approved_from: date | None = None
    approved_to: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.approved_from and self.approved_to and self.approved_from > self.approved_to:
            raise ValueError("invalid date range")
        return self


class WarehouseQuery(WarehouseFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort: Literal["approved_desc", "approved_asc"] = "approved_desc"


class BoxLineInput(Strict):
    box_type: Literal["A", "B", "C", "custom"]
    boxes: int = Field(strict=True, ge=1, le=9999)
    units_per_box: int = Field(strict=True, ge=1, le=100000)
    gross_weight_kg: Weight
    length_cm: Dimension | None = None
    width_cm: Dimension | None = None
    height_cm: Dimension | None = None

    @model_validator(mode="after")
    def dimensions(self):
        if self.box_type == "custom" and any(
            v is None for v in (self.length_cm, self.width_cm, self.height_cm)
        ):
            raise ValueError("custom dimensions required")
        return self


class BoxLineRead(BoxLineInput):
    id: UUID
    line_no: int


class PackageInput(Strict):
    length_cm: Annotated[Decimal, Field(ge=Decimal("0.1"), le=500, decimal_places=4)]
    width_cm: Annotated[Decimal, Field(ge=Decimal("0.1"), le=500, decimal_places=4)]
    height_cm: Annotated[Decimal, Field(ge=Decimal("0.1"), le=500, decimal_places=4)]
    gross_weight_g: Annotated[Decimal, Field(ge=1, le=100000, decimal_places=4)]
    net_weight_g: Annotated[Decimal, Field(ge=0, le=100000, decimal_places=4)] | None = None

    @model_validator(mode="after")
    def weights(self):
        if self.net_weight_g is not None and self.net_weight_g > self.gross_weight_g:
            raise ValueError("net exceeds gross")
        return self


class WarehouseCommand(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(strict=True, ge=1)
    idempotency_key: UUID


class BoxesCommand(WarehouseCommand):
    lines: list[BoxLineInput] = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)
    package: PackageInput | None = None

    @model_validator(mode="after")
    def bounded_total(self):
        if sum(r.boxes * r.units_per_box for r in self.lines) > 1000000:
            raise ValueError("packed total exceeds limit")
        return self


class ReboxCommand(BoxesCommand):
    confirm_extra: bool = Field(default=False, strict=True)
    reason: str = Field(min_length=2, max_length=500)
    expected_box_version: int = Field(strict=True, ge=1)
    reason_category: Literal["shortage", "damage", "box_capacity", "other"] | None = None

    @model_validator(mode="after")
    def change_reason(self):
        if len(self.reason.strip()) < 2:
            raise ValueError("rebox reason required")
        return self


class DoneCommand(WarehouseCommand):
    reason_category: Literal["shortage", "damage", "box_capacity", "other"] | None = None
    reason: str | None = Field(default=None, max_length=500)
    confirm_extra: bool = Field(default=False, strict=True)
    package: PackageInput | None = None
    expected_box_version: int = Field(strict=True, ge=1)
    requirement_version: str = Field(pattern=r"^[a-f0-9]{64}$")


class SupplementalInboundCommand(WarehouseCommand):
    inbound_order_sn: str = Field(pattern=r"^IB[A-Z0-9_-]{1,62}$")


class SupplementalSyncCommand(WarehouseCommand):
    pass


class UnpackedDispositionCommand(WarehouseCommand):
    action: Literal["resend", "void"]
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def void_reason(self):
        if self.action == "void" and len((self.reason or "").strip()) < 2:
            raise ValueError("void reason required")
        return self


class CustomsCommand(WarehouseCommand):
    value: bool = Field(strict=True)
    reason: str = Field(min_length=2, max_length=500)

    @model_validator(mode="after")
    def reason_text(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 2:
            raise ValueError("reason required")
        return self


class NoteCommand(WarehouseCommand):
    category: Literal[
        "arrival_incomplete",
        "labels",
        "materials",
        "operations",
        "schedule",
        "quality",
        "other",
        "resolved",
    ]
    text: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def note_text(self):
        self.text = self.text.strip()
        if self.category == "other" and len(self.text) < 2:
            raise ValueError("description required")
        return self


class ProductRequirement(Strict):
    state: Literal["complete", "missing", "unknown"]
    version: str
    source_snapshot_id: UUID | None = None
    package: PackageInput | None = None
    reason: str | None = None


class BoxSetRead(Strict):
    id: UUID
    version: int
    total_qty: int
    variance_qty: int
    variance_reason: str | None
    lines: list[BoxLineRead]
    completed_at: datetime | None
    completed_by: str | None
    package_snapshot: dict | None


class NoteRead(Strict):
    category: str
    category_label: str
    text: str
    resolved: bool
    actor_uid: str
    updated_at: datetime


class VarianceRead(Strict):
    proposed_lines: list[BoxLineInput] | None = None
    last_sync_code: str | None = None
    last_sync_gap: int | None = None
    notification_state: str | None = None
    kind: str
    state: str
    quantity: int
    gap_qty: int | None
    reason_category: str | None
    reason: str | None
    supplemental_ib: str | None


class ExtraAllocationRead(Strict):
    source_publication_id: UUID
    source_board_id: UUID
    inbound_order_sn: str
    quantity: int


class WarehouseOrderRead(Strict):
    extra_allocations: list[ExtraAllocationRead] = Field(default_factory=list)
    id: UUID
    source_account_ref: str
    version: int
    pk: str
    is_test: bool
    approved_at: datetime
    approved_date: date
    inbound_order_sn: str
    inbound_date: date | None
    arrival_date: date | None = None
    arrival_status: Literal["inbound_date", "unknown"] = "unknown"
    warehouse_days: int | None = None
    received_dates: list[date] = Field(default_factory=list)
    receipt_order_sns: list[str] = Field(default_factory=list)
    purchase_order_sns: list[str]
    sku: str
    product_name: str | None
    store_id: str | None
    store_name: str | None
    item_id: str | None
    gtin: str | None
    msku: str | None
    approved_quantity: int
    stock_balance: int | None
    balance_publication_id: UUID | None
    balance_observed_at: datetime | None
    status: Literal["todo", "packed"]
    packing_days: int
    customs_value: bool | None
    customs_src: str
    product_requirement: ProductRequirement
    box_set: BoxSetRead | None
    current_note: NoteRead | None
    variance_case: VarianceRead | None = None
    extra_available: int | None = None
    extra_publication_id: UUID | None = None
    command_outcome: Literal["saved", "completed", "blocked", "ready"] | None = None
    can_complete: bool
    completion_blocked_reasons: list[str]
    shipment_status: Literal["not_connected"] = "not_connected"
    boxspec_sync_status: Literal["not_connected"] = "not_connected"


class WarehouseList(Strict):
    items: list[WarehouseOrderRead]
    total: int


class WarehouseSummary(Strict):
    overpack_blocked: int = 0
    unpacked_pending: int = 0
    todo: int
    packed: int


class WarehouseOption(Strict):
    value: str
    label: str


class WarehouseOptions(Strict):
    stores: list[WarehouseOption]


class WarehouseEventRead(Strict):
    id: UUID
    kind: str
    actor_uid: str
    order_version: int
    occurred_at: datetime
    reason: str | None = None
    before: dict | None = None
    result: dict


class WarehouseEvents(Strict):
    items: list[WarehouseEventRead]
    total: int
