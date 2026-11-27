"""登记财务审批单同步任务（幂等）。不调飞书，不开定时。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import IntegrationCatalogService  # noqa: E402

AUTHORIZATION_ENV = "FINANCE_APPROVAL_BOOTSTRAP_AUTHORIZED"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("FINANCE_APPROVAL_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        with get_session_factory()() as session:
            statuses = IntegrationCatalogService(session).bootstrap_finance_approval_governance()
    except Exception:
        print("FINANCE_APPROVAL_BOOTSTRAP_FAILED")
        return 1
    print(f"interface_status={statuses[0]}")
    print(f"retention_policy_status={statuses[1]}")
    print(f"sync_config_status={statuses[2]}")
    print("schedule_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
