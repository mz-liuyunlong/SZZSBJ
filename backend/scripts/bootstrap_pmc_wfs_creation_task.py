"""在 数据中心 · 任务中心 注册「WFS 创建结果拉取」（每个领星账号一行配置）。

只写治理表（接口 + 同步配置），不调用 Walmart / 领星。自动同步默认关闭，由管理员在任务中心
打开；频率默认每 3 分钟（cron ``*/3 * * * *``，UTC）。可重复执行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.pmc_wfs.creation_task import bootstrap  # noqa: E402

AUTHORIZATION_ENV = "PMC_WFS_CREATION_TASK_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_WFS_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_WFS_CREATION_TASK_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    account = os.getenv(SOURCE_ACCOUNT_ENV, "").strip()
    if not account:
        print("PMC_WFS_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2
    try:
        register_productlist_sync_models()
        with get_session_factory()() as session:
            interface_status, config_status = bootstrap(session, account)
    except Exception as error:
        print("PMC_WFS_CREATION_TASK_BOOTSTRAP_FAILED", type(error).__name__)
        return 1
    print(f"wfsCreationResultPoll: interface={interface_status} config={config_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
