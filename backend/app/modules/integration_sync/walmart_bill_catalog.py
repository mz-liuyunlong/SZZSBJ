"""沃尔玛账单同步（领星 statement/list）的接口登记常量。

回款对账、现金利润、结算利润三个板块共用这一份账单数据，只拉一次。
Rocky 2026-11-08：只用领星账单接口（不接 payout/list）；每周自动拉一次 + 页面「手动同步」。
"""

from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint

RequestKind = Literal["offset_page"]


@dataclass(frozen=True, slots=True)
class WalmartBillSyncInterfaceSpec:
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


# 打开同步后的定时：每周三上海时间 03:00（cron 按 UTC，即周二 19:00；2 是周二）。
# 领星同步沃尔玛有 1~3 天延迟，账单是双周出，每周拉一次、每次重拉最近 35 天够用。
WALMART_BILL_SCHEDULE_CRON: Final = "0 19 * * 2"

# 每次自动 / 手动同步重拉最近多少天（按「交易日期」）。
WALMART_BILL_ROLLING_DAYS: Final = 35

# 发现某期账单的明细延伸到窗口最早一天，就再往前补一个月，最多补这么多次（防止无限往前）。
WALMART_BILL_MAX_EXTENSIONS: Final = 12

# 回填最早从这一天开始（Rocky：历史从 2026-03 开始）。
WALMART_BILL_EARLIEST_DATE: Final = "2026-03-01"

# max_pages 是「一个店、一个时间段」最多翻多少页；超过就把时间段对半切开再拉。
WALMART_BILL_SYNC_SPEC: Final = WalmartBillSyncInterfaceSpec(
    interface_key="walmartBillStatementList",
    display_name="沃尔玛账单同步",
    endpoint_path="/basicOpen/multiplatformFinance/walmart/bill/statement/list",
    request_kind="offset_page",
    handler_key="lingxing.walmart_bill_statement.v1",
    target_table="ods_lingxing_walmart_bill_lines",
    retention_policy_key="lingxing-walmart-bill-statement-v1",
    default_page_size=200,
    default_max_pages=500,
)
