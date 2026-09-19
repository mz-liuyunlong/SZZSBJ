"""Create disabled governance rows for the PMC purchase-board interfaces (Gate 2, PR-C).

Catalog-only. Every row is created with outbound_enabled=False, is_enabled=False and
schedule_enabled=False. Running this never authorizes a Lingxing call, a schedule or a
production run; each of those needs its own owner authorization and runbook entry.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    IntegrationCatalogService,
    PmcPurchaseGovernanceBootstrapError,
    validate_pmc_purchase_source_account_ref,
)
from app.modules.integration_sync.pmc_purchase_catalog import (  # noqa: E402
    PMC_PURCHASE_PAGE_SIZE,
    PMC_PURCHASE_SYNC_INTERFACE_SPECS,
)

AUTHORIZATION_ENV = "PMC_PURCHASE_GOVERNANCE_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_PURCHASE_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_PURCHASE_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_pmc_purchase_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except PmcPurchaseGovernanceBootstrapError as error:
        print(str(error))
        return 2

    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_pmc_purchase_governance(
                source_account_ref
            )
    except Exception:
        print("PMC_PURCHASE_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1

    for spec, interface_status, policy_status, config_status in zip(
        PMC_PURCHASE_SYNC_INTERFACE_SPECS,
        result.interface_statuses,
        result.retention_policy_statuses,
        result.sync_config_statuses,
        strict=True,
    ):
        print(
            f"{spec.interface_key}: interface={interface_status} "
            f"retention_policy={policy_status} sync_config={config_status}"
        )
    print("source_account_ref_present=true")
    print("outbound_enabled=false")
    print("is_enabled=false")
    print("schedule_enabled=false")
    print(f"page_size={PMC_PURCHASE_PAGE_SIZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
