"""Create disabled governance rows for the settlement-profit PR-2 syncs.

Three Lingxing interfaces: shippingList v2 / shippingDetail / wmsOrderList.
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
from app.modules.integration_sync.fin_shipping_catalog import FIN_SHIPPING_SYNC_SPECS  # noqa: E402

AUTHORIZATION_ENV = "FIN_SHIPPING_GOVERNANCE_BOOTSTRAP_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "FIN_SHIPPING_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("FIN_SHIPPING_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_data_pages_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except DataPagesGovernanceBootstrapError:
        print("FIN_SHIPPING_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2
    try:
        with get_session_factory()() as session:
            result = IntegrationCatalogService(session).bootstrap_fin_shipping_governance(
                source_account_ref
            )
    except Exception:
        print("FIN_SHIPPING_GOVERNANCE_BOOTSTRAP_FAILED")
        return 1
    for index, spec in enumerate(FIN_SHIPPING_SYNC_SPECS):
        print(
            f"{spec.interface_key}: interface={result.interface_statuses[index]} "
            f"retention_policy={result.retention_policy_statuses[index]} "
            f"sync_config={result.sync_config_statuses[index]}"
        )
    print("outbound_enabled=false")
    print("is_enabled=false")
    print("schedule_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
