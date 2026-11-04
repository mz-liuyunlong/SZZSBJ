"""Count-based contracts with automatic validation approval; no manual approval input."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.modules.pmc_domestic.warehouse_schemas import Strict
from app.modules.pmc_wfs.schemas import ReturnAddress

Count = Annotated[int, Field(strict=True, ge=1, le=9999)]
State = Literal[
    "AWAITING_APPROVAL", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN", "PARTIAL"
]


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


class ApprovalCommand(Strict):
    """Human approval of one creation operation (red line: written, per operation)."""

    approval_ref: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][\w.:/#-]*$")


class CreationCommand(AllocationCommand):
    source_account_ref: str = Field(min_length=1, max_length=128)
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID
    return_address: ReturnAddress
    # Empty = WFS 设置 · 创建默认值 (today + ship_date_offset days).
    expected_delivery_at: AwareDatetime | None = None
    its: bool = Field(strict=True, default=False)


class ShipmentRead(Strict):
    shipment_id: str
    label_state: Literal["PENDING", "READY", "FAILED"] = "PENDING"
    fc: str | None = None  # Walmart 分配的仓库（创建返回）


class TicketRead(Strict):
    id: UUID
    number: int
    inbound_order_id: str | None = None  # 我方单号 = Walmart inboundOrderId（提交后才有）
    state: State
    allocation: AllocationTicket
    shipments: list[ShipmentRead]
    error_code: str | None = None
    error_message: str | None = None  # Walmart's reason or ours, shown to users
    submissions: int = 0
    polls: int | None = None  # read-backs done while 提交中 (every 3 min, max 10)
    max_polls: int | None = None
    next_poll_at: datetime | None = None


class OperationRead(Strict):
    id: UUID
    order_id: UUID
    state: State
    created_at: datetime
    tickets: list[TicketRead]
    approval_mode: Literal["manual"] = "manual"
    automatic_checks_at: datetime | None = None
    approval_ref: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None


class OperationList(Strict):
    items: list[OperationRead]
    total: int


class Capabilities(Strict):
    creation_enabled: bool
    preview_enabled: bool
    reason: str | None = None
    mode: Literal["off", "probe", "single", "batch", "simulator"] = "off"
    # 本机模拟通道（只在 APP_ENV=local），页面据此显示横幅和「立即拉取结果」
    simulator: bool = False


class CreationDefaultsRead(Strict):
    """创建默认值（按店铺 → 账号 → 8088 默认），创建弹窗自动带出。"""

    source_account_ref: str
    store_id: str | None = None
    transport: str
    ship_date_offset: int
    pallet_boxes: int
    mixed_boxes: int
    carrier_opt: str
    its: bool = False
    return_address: ReturnAddress | None = None
    saved: bool
    level: Literal["store", "common", "account", "default"] = "default"
    expected_delivery_date: str  # today + ship_date_offset (Asia/Shanghai)


class ProbeResult(Strict):
    ok: bool
    status_code: int
    store_code: str
    recent_shipments: int
    # 用一个不可能存在的单号查一次：要返回"查无此单"（8088 是 204），首次提交前的查单才可靠。
    lookup_status_code: int | None = None
    lookup_not_found_ok: bool | None = None


class SimulatorPull(Strict):
    """「立即拉取结果（本机模拟）」：这次触发的任务中心运行。"""

    run_ids: list[UUID]
