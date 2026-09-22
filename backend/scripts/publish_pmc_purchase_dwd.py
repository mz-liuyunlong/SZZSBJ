"""Publish the current PMC purchase documents from ODS into the DWD tables (Gate 3, G3-B).

Manual, one account per invocation, gated by PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED=true.
Reads only ODS rows of succeeded runs; writes dwd_purchase_* plus gov_parse_jobs and
gov_data_lineage; prints counts only. It never calls Lingxing, never touches governance
rows and never schedules anything. Running it in production still requires a runbook
entry and the Owner's written authorization.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcPurchaseGovernanceBootstrapError,
    validate_pmc_purchase_source_account_ref,
)
from app.modules.pmc_purchase.publisher import (  # noqa: E402
    PmcPurchaseDwdPublisher,
    PmcPurchaseDwdPublishError,
)

AUTHORIZATION_ENV = "PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_PURCHASE_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_PURCHASE_DWD_PUBLISH_REQUIRES_AUTHORIZATION")
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
            result = PmcPurchaseDwdPublisher(session).publish(source_account_ref=source_account_ref)
    except PmcPurchaseDwdPublishError as error:
        print(str(error))
        return 1
    except Exception:
        print("PMC_PURCHASE_DWD_PUBLISH_FAILED")
        return 1

    print(f"builder_version={result.builder_version}")
    print(result.as_message())
    print(f"build_report: {result.report.as_message()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
