"""Create disabled governance rows for the WFS settlement collector.

Catalog-only. This command never authorizes provider traffic, scheduling, case
creation, or a production migration; those remain separate Owner gates.
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
from app.modules.integration_sync.wfs_catalog import WFS_SETTLEMENT_SYNC_SPEC  # noqa: E402

AUTHORIZATION_ENV = "WFS_GOVERNANCE_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "WFS_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("WFS_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_data_pages_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except DataPagesGovernanceBootstrapError:
        print("WFS_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2

    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_wfs_governance(source_account_ref)
    except Exception:
        print("WFS_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1

    print(f"interface_status={result.interface_statuses[0]}")
    print(f"retention_policy_status={result.retention_policy_statuses[0]}")
    print(f"sync_config_status={result.sync_config_statuses[0]}")
    print("source_account_ref_present=true")
    print("outbound_enabled=false")
    print("is_enabled=false")
    print("schedule_enabled=false")
    print(f"page_size={WFS_SETTLEMENT_SYNC_SPEC.default_page_size}")
    print(f"max_pages={WFS_SETTLEMENT_SYNC_SPEC.default_max_pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
