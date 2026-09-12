from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    IntegrationCatalogService,
    ProductListGovernanceBootstrapError,
    validate_productlist_source_account_ref,
)


def main() -> int:
    if os.getenv("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_AUTHORIZED", "").casefold() != "true":
        print("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_productlist_source_account_ref(
            os.getenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", "")
        )
    except ProductListGovernanceBootstrapError as error:
        print(str(error))
        return 2

    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_productlist_governance(
                source_account_ref
            )
    except Exception:
        print("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1

    print(f"interface_status={result.interface_status}")
    print(f"retention_policy_status={result.retention_policy_status}")
    print(f"sync_config_status={result.sync_config_status}")
    print("source_account_ref_present=true")
    print("schedule_enabled=false")
    print("page_size=1000")
    print("max_pages=10000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
