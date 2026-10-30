"""Count-based contracts with automatic validation approval; no manual approval input."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.modules.pmc_domestic.warehouse_schemas import Strict
from app.modules.pmc_wfs.schemas import ReturnAddress

Count = Annotated[int, Field(strict=True, ge=1, le=9999)]
State = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN", "PARTIAL"]


class OrderSelection(Strict):
    order_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    expected_box_version: int = Field(strict=True, ge=1)


class AllocationCommand(OrderSelection):
    additional_selections: list[OrderSelection] = Field(default_factory=list, max_length=99)
    shipping_boxes: Count
    shipment_count: Count
    shipment_boxes: list[Count] = Field(min_length=1, max_length=9999)

    @model_validator(mode="after")
    def conserved(self):
        ids = [self.order_id, *(s.order_id for s in self.additional_selections)]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate packing order")
        if len(self.shipment_boxes) != self.shipment_count:
            raise ValueError("shipment count does not match allocations")
        if sum(self.shipment_boxes) != self.shipping_boxes:
            raise ValueError("box allocations must sum to shipping boxes")
        return self


class BoxRange(Strict):
    order_id: UUID
    pk: str
    sku: str
    box_version: int
    line_id: UUID
    line_no: int
    start: int
    end: int
    boxes: int
    units_per_box: int
    units: int
    length_cm: str
    width_cm: str
    height_cm: str
    gross_weight_kg: str


class AllocationTicket(Strict):
    number: int
    boxes: int
    units: int
    ranges: list[BoxRange]


class AllocationPreview(Strict):
    order_id: UUID
    order_version: int
    box_version: int
    selections: list[OrderSelection]
    available_boxes: int
    remaining_boxes: int
    tickets: list[AllocationTicket]
    preview_hash: str


class CreationCommand(AllocationCommand):
    source_account_ref: str = Field(min_length=1, max_length=128)
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID
    return_address: ReturnAddress
    expected_delivery_at: AwareDatetime
    its: bool = Field(strict=True, default=False)


class ShipmentRead(Strict):
    shipment_id: str
    label_state: Literal["PENDING", "READY", "FAILED"] = "PENDING"


class TicketRead(Strict):
    id: UUID
    number: int
    state: State
    allocation: AllocationTicket
    shipments: list[ShipmentRead]
    error_code: str | None = None


class OperationRead(Strict):
    id: UUID
    order_id: UUID
    state: State
    created_at: datetime
    tickets: list[TicketRead]
    approval_mode: Literal["automatic"] = "automatic"
    automatically_approved_at: datetime | None = None


class OperationList(Strict):
    items: list[OperationRead]
    total: int


class Capabilities(Strict):
    creation_enabled: bool
    preview_enabled: bool
    reason: str | None = None
