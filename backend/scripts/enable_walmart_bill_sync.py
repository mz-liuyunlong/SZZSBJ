"""Turn on the Walmart bill sync. The script itself sends no request.

两步，各要负责人授权：
1. 只开手动（默认）：WALMART_BILL_SYNC_ENABLE_AUTHORIZED=true
   → 任务中心和回款对账的「手动同步」可用，定时不开；首次手动同步当作受控探测。
2. 开每周定时：再加 WALMART_BILL_SYNC_SCHEDULE_AUTHORIZED=true 重跑本脚本 → 之后每周自动调领星。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    DataPagesGovernanceBootstrapError,
    IntegrationCatalogService,
    validate_data_pages_source_account_ref,
)

AUTHORIZATION_ENV = "WALMART_BILL_SYNC_ENABLE_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "WALMART_BILL_SOURCE_ACCOUNT_REF"
SCHEDULE_ENV = "WALMART_BILL_SYNC_SCHEDULE_AUTHORIZED"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("WALMART_BILL_SYNC_ENABLE_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_data_pages_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except DataPagesGovernanceBootstrapError:
        print("WALMART_BILL_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2
    schedule = os.getenv(SCHEDULE_ENV, "").casefold() == "true"
    try:
        with get_session_factory()() as session:
            enabled = IntegrationCatalogService(session).enable_walmart_bill_sync(
                source_account_ref, schedule=schedule
            )
    except Exception:
        print("WALMART_BILL_SYNC_ENABLE_FAILED")
        return 1
    if not enabled:
        print("WALMART_BILL_GOVERNANCE_NOT_BOOTSTRAPPED")
        return 1
    print("outbound_enabled=true")
    print("is_enabled=true")
    print(f"schedule_enabled={'true' if schedule else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
