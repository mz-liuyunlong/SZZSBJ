"""任务中心目录：WFS 费用报表同步（沃尔玛接口，Rocky 2026-11-13 批准）。

只登记接口和配置；定时默认关闭，在任务中心打开（建议每小时一次，UTC cron「0 * * * *」：
到期要不要拉由任务自己按期判断，每小时一次只是让「下单 → 等生成 → 下载」能往前走）。
远端执行另有两道开关：SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED、SZZSBJ_WALMART_WFS_REPORTS_ENABLED。
"""

from dataclasses import dataclass
from typing import Final

WFS_REPORT_PROVIDER: Final = "walmart"
WFS_REPORT_SOURCE_REF: Final = "walmart-wfs-fee-reports"


@dataclass(frozen=True, slots=True)
class WfsReportSyncSpec:
    interface_key: str
    display_name: str
    method: str
    endpoint_path: str
    request_kind: str
    handler_key: str
    target_table: str
    retention_policy_key: str
    default_page_size: int
    default_max_pages: int


WFS_REPORT_SYNC_SPEC: Final = WfsReportSyncSpec(
    interface_key="walmartWfsFeeReports",
    display_name="WFS 费用报表同步（沃尔玛）",
    method="GET",
    endpoint_path="/v3/reports/reportRequests",
    request_kind="offset_page",
    handler_key="walmart.wfs_fee_reports.v1",
    target_table="ops_walmart_wfs_report_jobs",
    retention_policy_key="walmart-wfs-fee-reports-v1",
    default_page_size=100,
    default_max_pages=1,
)
