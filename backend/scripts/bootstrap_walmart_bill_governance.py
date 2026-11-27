"""Create disabled governance rows for the Walmart bill sync (Lingxing statement/list).

Catalog-only. This command never authorizes provider traffic or scheduling;
turning on outbound and the first run remain separate Owner gates.
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

AUTHORIZATION_ENV = "WALMART_BILL_GOVERNANCE_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "WALMART_BILL_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("WALMART_BILL_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_data_pages_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except DataPagesGovernanceBootstrapError:
        print("WALMART_BILL_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2
    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_walmart_bill_governance(
                source_account_ref
            )
    except Exception:
        print("WALMART_BILL_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1
    print(f"interface_status={result.interface_statuses[0]}")
    print(f"retention_policy_status={result.retention_policy_statuses[0]}")
    print(f"sync_config_status={result.sync_config_statuses[0]}")
    print("outbound_enabled=false")
    print("is_enabled=false")
    print("schedule_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
