from dataclasses import dataclass
from typing import Final, Literal

from app.integrations.lingxing.client import LingxingEndpoint

RequestKind = Literal["offset_page"]


@dataclass(frozen=True, slots=True)
class FxSyncInterfaceSpec:
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


# 打开同步时用的定时：每周一上海时间 02:00（cron 按 UTC，即周日 18:00；0 是周日）。
# Rocky 2026-11-05 定每周一次。领星的月汇率会在月后不固定的日子被人改，最多晚一周同步到。
FX_RATE_SCHEDULE_CRON: Final = "0 18 * * 0"

# max_pages 在这里表示往回拉几个月（含当月），page_size 固定 1：一个月一次请求。
FX_RATE_SYNC_SPEC: Final = FxSyncInterfaceSpec(
    interface_key="lingxingFxRate",
    display_name="领星月汇率同步",
    endpoint_path="/erp/sc/routing/finance/currency/currencyMonth",
    request_kind="offset_page",
    handler_key="lingxing.finance.currency_month.v1",
    target_table="fact_lingxing_fx_rate",
    retention_policy_key="lingxing-finance-currency-month-v1",
    default_page_size=1,
    default_max_pages=13,
)
