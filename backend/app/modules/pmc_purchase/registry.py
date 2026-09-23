"""Implementation registry for the PMC purchase board read API (Gate 3, G3-E).

Mirrors ``data_pages.registry``: one stable entry per route so acceptance, the API
document and the data-interface registry can be checked against code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PurchaseApiKey = Literal["board", "board_summary", "order_detail", "sku_cycles", "pending_plans"]

READ_ONLY_BOUNDARY: Final = (
    "Read-only DWS/DWD API; no Lingxing call, no ODS/RAW read, no write, no Celery task, "
    "no production migration or production database operation."
)
EMPTY_DATA_BEHAVIOR: Final = "Return a successful envelope with empty items and meta.total=0."


@dataclass(frozen=True, slots=True)
class PurchaseApiRegistryEntry:
    key: PurchaseApiKey
    prp_ref: str
    route_path: str
    permission: str
    source_objects: tuple[str, ...]
    demo_ref: str
    empty_data_behavior: str
    current_boundary: str


PERMISSION_READ: Final = "pmc:purchase:read"

PMC_PURCHASE_API_REGISTRY: Final[dict[PurchaseApiKey, PurchaseApiRegistryEntry]] = {
    "board": PurchaseApiRegistryEntry(
        key="board",
        prp_ref="PRPs/pmc-purchase-board.md §7.1",
        route_path="/api/pmc/purchase/board",
        permission=PERMISSION_READ,
        source_objects=("dws_purchase_board",),
        demo_ref="Demo v1.4 主表 + 筛选栏",
        empty_data_behavior=EMPTY_DATA_BEHAVIOR,
        current_boundary=READ_ONLY_BOUNDARY,
    ),
    "board_summary": PurchaseApiRegistryEntry(
        key="board_summary",
        prp_ref="PRPs/pmc-purchase-board.md §7.2",
        route_path="/api/pmc/purchase/board/summary",
        permission=PERMISSION_READ,
        source_objects=("dws_purchase_board", "dws_purchase_sku_cycle", "dwd_purchase_plan"),
        demo_ref="Demo v1.4 七张统计卡",
        empty_data_behavior="Return zero counters and as_of.",
        current_boundary=READ_ONLY_BOUNDARY,
    ),
    "order_detail": PurchaseApiRegistryEntry(
        key="order_detail",
        prp_ref="PRPs/pmc-purchase-board.md §7.3",
        route_path="/api/pmc/purchase/orders/{order_sn}",
        permission=PERMISSION_READ,
        source_objects=("dws_purchase_board", "dws_purchase_sku_cycle", "dwd_purchase_plan"),
        demo_ref="Demo v1.4 采购单详情 Modal",
        empty_data_behavior="404 NOT_FOUND when the order has no board row in scope.",
        current_boundary=READ_ONLY_BOUNDARY,
    ),
    "sku_cycles": PurchaseApiRegistryEntry(
        key="sku_cycles",
        prp_ref="PRPs/pmc-purchase-board.md §7.4",
        route_path="/api/pmc/purchase/sku-cycles",
        permission=PERMISSION_READ,
        source_objects=("dws_purchase_sku_cycle",),
        demo_ref="Demo v1.4 实际采购交期悬浮（近 5 单）",
        empty_data_behavior="items=[] and the requested SKUs listed in data.missing.",
        current_boundary=READ_ONLY_BOUNDARY,
    ),
    "pending_plans": PurchaseApiRegistryEntry(
        key="pending_plans",
        prp_ref="PRPs/pmc-purchase-board.md §7.2（待采购超时卡片下钻）",
        route_path="/api/pmc/purchase/plans/pending",
        permission=PERMISSION_READ,
        source_objects=("dwd_purchase_plan", "dws_purchase_board", "dim_lingxing_stores"),
        demo_ref="Demo v1.4 待采购超时（S2）弹窗：计划待采购",
        empty_data_behavior=EMPTY_DATA_BEHAVIOR,
        current_boundary=READ_ONLY_BOUNDARY,
    ),
}
