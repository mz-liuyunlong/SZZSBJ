"""Publish receipt ODS into domestic batch DWD (phase 1).

Requires ``PMC_DOMESTIC_DWD_PUBLISH_AUTHORIZED=true`` and
``PMC_DOMESTIC_SOURCE_ACCOUNT_REF``. Does not call Lingxing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcDomesticGovernanceBootstrapError,
    validate_pmc_domestic_source_account_ref,
)
from app.modules.pmc_domestic.publisher import (  # noqa: E402
    PmcDomesticDwdPublisher,
    PmcDomesticDwdPublishError,
)

AUTHORIZATION_ENV = "PMC_DOMESTIC_DWD_PUBLISH_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "PMC_DOMESTIC_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("PMC_DOMESTIC_DWD_PUBLISH_REQUIRES_AUTHORIZATION")
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
            result = PmcDomesticDwdPublisher(session).publish(
                source_account_ref=source_account_ref
            )
    except PmcDomesticDwdPublishError as error:
        print(str(error))
        return 1
    except Exception:
        print("PMC_DOMESTIC_DWD_PUBLISH_FAILED")
        return 1

    print(f"builder_version={result.builder_version}")
    print(result.as_message())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
