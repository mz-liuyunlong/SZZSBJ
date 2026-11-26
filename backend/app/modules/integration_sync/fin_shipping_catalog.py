"""结算利润 PR-2：财务发货单 / 发货单明细 / 销售出库单三个领星接口的登记常量。

订单审核（货本、头程）和结算利润（非 WFS 尾程物流费）共用这三份数据，只拉一次。
Rocky 2026-11-26：默认关闭；每周和沃尔玛账单同步一起跑；滚动重拉最近 90 天；
历史从 2026-05 回填（回填单独授权）。落到 #365 的三张 ODS 表，原始响应进 ods_api_raw_blobs。
"""

from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint

RequestKind = Literal["offset_page"]


@dataclass(frozen=True, slots=True)
class FinShippingSyncInterfaceSpec:
    interface_key: str
    display_name: str
    endpoint_path: LingxingEndpoint
    request_kind: RequestKind
    handler_key: str
    target_table: str
    retention_policy_key: str
    default_page_size: int
    default_max_pages: int
    schedule_cron: str
    initial_outbound_enabled: bool = False
    schedule_enabled: bool = False


# 打开定时后三个接口错开跑（cron 按 UTC；2 是周二；上海 = UTC+8）：
# 发货单 周三 04:00、出库单 04:30、明细 05:00 —— 明细读的是发货单同步的结果，必须排在发货单之后；
# 三个接口各自一把执行锁，同一时刻排也会并行，所以靠错开时间保证顺序。沃尔玛账单同步在周三 03:00。
FIN_SHIPPING_LIST_SCHEDULE_CRON: Final = "0 20 * * 2"
FIN_WMS_OUTBOUND_SCHEDULE_CRON: Final = "30 20 * * 2"
FIN_SHIPPING_DETAIL_SCHEDULE_CRON: Final = "0 21 * * 2"

# 每次自动 / 手动同步重拉最近多少天（发货单按发货时间，出库单按变更时间）。
FIN_SHIPPING_ROLLING_DAYS: Final = 90

# 回填最早从这一天开始（Rocky：历史从 2026-05 开始）。
FIN_SHIPPING_EARLIEST_DATE: Final = "2026-05-01"

# 发货单列表：offset/length 翻页，一个店一个时间段最多翻 max_pages 页。
FIN_SHIPPING_LIST_SYNC_SPEC: Final = FinShippingSyncInterfaceSpec(
    interface_key="finShippingList",
    display_name="财务发货单同步",
    endpoint_path="/basicOpen/multiplatform/query/shippingList",
    request_kind="offset_page",
    handler_key="lingxing.fin_shipping_list.v1",
    target_table="ods_lingxing_fin_shipping_lists",
    retention_policy_key="lingxing-fin-shipping-list-v1",
    default_page_size=100,
    default_max_pages=200,
    schedule_cron=FIN_SHIPPING_LIST_SCHEDULE_CRON,
)

# 发货单明细：不分页，一张发货单一次请求；max_pages 表示一次运行最多拉多少张发货单的明细，
# page_size 固定 1。
FIN_SHIPPING_DETAIL_SYNC_SPEC: Final = FinShippingSyncInterfaceSpec(
    interface_key="finShippingDetail",
    display_name="财务发货单明细同步",
    endpoint_path="/basicOpen/multiplatform/query/shippingDetail",
    request_kind="offset_page",
    handler_key="lingxing.fin_shipping_detail.v1",
    target_table="ods_lingxing_fin_shipping_detail_items",
    retention_policy_key="lingxing-fin-shipping-detail-v1",
    default_page_size=1,
    default_max_pages=2000,
    schedule_cron=FIN_SHIPPING_DETAIL_SCHEDULE_CRON,
)

# 销售出库单：page/page_size 翻页。
FIN_WMS_OUTBOUND_SYNC_SPEC: Final = FinShippingSyncInterfaceSpec(
    interface_key="finWmsOutboundOrders",
    display_name="财务销售出库单同步",
    endpoint_path="/erp/sc/routing/wms/order/wmsOrderList",
    request_kind="offset_page",
    handler_key="lingxing.fin_wms_outbound.v1",
    target_table="ods_lingxing_fin_wms_outbound_orders",
    retention_policy_key="lingxing-fin-wms-outbound-v1",
    default_page_size=200,
    default_max_pages=200,
    schedule_cron=FIN_WMS_OUTBOUND_SCHEDULE_CRON,
)

FIN_SHIPPING_SYNC_SPECS: Final = (
    FIN_SHIPPING_LIST_SYNC_SPEC,
    FIN_SHIPPING_DETAIL_SYNC_SPEC,
    FIN_WMS_OUTBOUND_SYNC_SPEC,
)
