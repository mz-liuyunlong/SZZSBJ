"""任务中心目录：财务审批单同步（飞书）。

审批定义编码不进仓库，从环境变量 FINANCE_APPROVAL_CODES 读。
飞书应用只从 FEISHU_APP_ID / FEISHU_APP_SECRET 读。
"""

from dataclasses import dataclass
from typing import Final

FINANCE_APPROVAL_PROVIDER: Final = "feishu"
FINANCE_APPROVAL_SOURCE_REF: Final = "feishu-finance-approval"


@dataclass(frozen=True, slots=True)
class FinanceApprovalSyncSpec:
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
    lookback_days: int


FINANCE_APPROVAL_SYNC_SPEC: Final = FinanceApprovalSyncSpec(
    interface_key="financeApprovalInstances",
    display_name="财务审批单同步（飞书）",
    method="GET",
    endpoint_path="/open-apis/approval/v4/instances",
    request_kind="offset_page",
    handler_key="feishu.finance_approval.v1",
    target_table="std_finance_feishu_approvals",
    retention_policy_key="feishu-finance-approval-v1",
    default_page_size=100,
    default_max_pages=50,
    lookback_days=90,
)

FINANCE_APPROVAL_KINDS: Final = ("费用报销", "付款申请", "备用金申请", "备用金核销")
ERR_CODES_NOT_CONFIGURED: Final = "SYNC_FEISHU_APPROVAL_CODES_NOT_CONFIGURED"


class FinanceApprovalCodesError(ValueError):
    """审批定义编码没配置或不完整；消息只有固定错误码，不带配置值。"""

    def __init__(self) -> None:
        super().__init__(ERR_CODES_NOT_CONFIGURED)


def parse_finance_approval_codes(raw: str | None) -> dict[str, str]:
    """解析「费用报销=…,付款申请=…,备用金申请=…,备用金核销=…」；四类必须齐全，不能有别的类型。"""
    codes: dict[str, str] = {}
    for part in (raw or "").split(","):
        if not part.strip():
            continue
        kind, separator, code = part.partition("=")
        kind, code = kind.strip(), code.strip()
        if not separator or not code or kind not in FINANCE_APPROVAL_KINDS or kind in codes:
            raise FinanceApprovalCodesError
        codes[kind] = code
    if set(codes) != set(FINANCE_APPROVAL_KINDS):
        raise FinanceApprovalCodesError
    return {kind: codes[kind] for kind in FINANCE_APPROVAL_KINDS}
