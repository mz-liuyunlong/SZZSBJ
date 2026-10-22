"""Create disabled governance rows for domestic warehouse Lingxing interfaces."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    IntegrationCatalogService,
    PmcDomesticGovernanceBootstrapError,
    validate_pmc_domestic_source_account_ref,
)
from app.modules.integration_sync.pmc_domestic_catalog import (  # noqa: E402
    PMC_DOMESTIC_SYNC_INTERFACE_SPECS,
)

AUTHORIZATION_ENV = "PMC_DOMESTIC_GOVERNANCE_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_DOMESTIC_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_DOMESTIC_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_pmc_domestic_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except PmcDomesticGovernanceBootstrapError as error:
        print(str(error))
        return 2

    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_pmc_domestic_governance(
                source_account_ref
            )
    except Exception:
        print("PMC_DOMESTIC_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1

    for spec, interface_status, policy_status, config_status in zip(
        PMC_DOMESTIC_SYNC_INTERFACE_SPECS,
        result.interface_statuses,
        result.retention_policy_statuses,
        result.sync_config_statuses,
        strict=True,
    ):
        print(
            f"{spec.interface_key}: interface={interface_status} "
            f"retention={policy_status} config={config_status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
