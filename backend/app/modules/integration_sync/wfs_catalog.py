from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint

RequestKind = Literal["offset_page"]


@dataclass(frozen=True, slots=True)
class WfsSyncInterfaceSpec:
    interface_key: str
    display_name: str
    endpoint_path: LingxingEndpoint
    request_kind: RequestKind
    handler_key: str
    target_table: str
    retention_policy_key: str
    default_page_size: int
    default_max_pages: int
    initial_outbound_enabled: bool = False
    schedule_enabled: bool = False


WFS_SETTLEMENT_SYNC_SPEC: Final = WfsSyncInterfaceSpec(
    interface_key="wfsProfitOrder",
    display_name="WFS 结算费用同步",
    endpoint_path="/basicOpen/multiplatform/profit/report/order",
    request_kind="offset_page",
    handler_key="lingxing.wfs.profit_order.v1",
    target_table="fact_walmart_wfs_fee_actual",
    retention_policy_key="lingxing-wfs-profit-order-v1",
    default_page_size=20,
    default_max_pages=500,
)
