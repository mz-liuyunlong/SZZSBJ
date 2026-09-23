"""Rebuild the PMC purchase board DWS tables from DWD (Gate 3, G3-D).

Manual, one account per invocation, gated by PMC_PURCHASE_DWS_REFRESH_AUTHORIZED=true.
Reads dwd_purchase_* / manual_purchase_cycle_override / rule_purchase_thresholds and the
store, listing and product-info dimensions plus succeeded-run ODS receipt rows; rewrites
dws_purchase_board / dws_purchase_sku_cycle / dws_purchase_pending for that account
(delete + insert); prints counts only. It never writes DWD, manual or rule rows, never
calls Lingxing and never schedules anything. Running it in production still requires a
runbook entry and the Owner's written authorization.

Optional: PMC_PURCHASE_DWS_AS_OF=YYYY-MM-DD fixes the calculation date (default: today, UTC).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcPurchaseGovernanceBootstrapError,
    validate_pmc_purchase_source_account_ref,
)
from app.modules.pmc_purchase.refresh import (  # noqa: E402
    PmcPurchaseDwsRefresher,
    PmcPurchaseDwsRefreshError,
)

AUTHORIZATION_ENV = "PMC_PURCHASE_DWS_REFRESH_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_PURCHASE_SOURCE_ACCOUNT_REF"
AS_OF_ENV = "PMC_PURCHASE_DWS_AS_OF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_PURCHASE_DWS_REFRESH_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_pmc_purchase_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except PmcPurchaseGovernanceBootstrapError as error:
        print(str(error))
        return 2
    as_of: date | None = None
    raw_as_of = os.getenv(AS_OF_ENV, "").strip()
    if raw_as_of:
        try:
            as_of = date.fromisoformat(raw_as_of)
        except ValueError:
            print("PMC_PURCHASE_DWS_AS_OF_INVALID")
            return 2

    try:
        with get_session_factory()() as session:
            result = PmcPurchaseDwsRefresher(session).refresh(
                source_account_ref=source_account_ref, today=as_of
            )
    except PmcPurchaseDwsRefreshError as error:
        print(str(error))
        return 1
    except Exception:
        print("PMC_PURCHASE_DWS_REFRESH_FAILED")
        return 1

    print(result.as_message())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
