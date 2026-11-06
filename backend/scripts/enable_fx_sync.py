"""Turn on the Lingxing monthly FX sync: task-centre manual runs and the weekly schedule.

Needs the Owner's authorization for production, because the schedule then calls Lingxing every
week on its own. The script itself sends no request.
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

AUTHORIZATION_ENV = "FX_SYNC_ENABLE_AUTHORIZED"
SOURCE_ACCOUNT_ENV = "FX_SOURCE_ACCOUNT_REF"


def main() -> int:
    if os.getenv(AUTHORIZATION_ENV, "").casefold() != "true":
        print("FX_SYNC_ENABLE_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = validate_data_pages_source_account_ref(
            os.getenv(SOURCE_ACCOUNT_ENV, "")
        )
    except DataPagesGovernanceBootstrapError:
        print("FX_SOURCE_ACCOUNT_REF_REQUIRED")
        return 2
    try:
        with get_session_factory()() as session:
            enabled = IntegrationCatalogService(session).enable_fx_sync(source_account_ref)
    except Exception:
        print("FX_SYNC_ENABLE_FAILED")
        return 1
    if not enabled:
        print("FX_GOVERNANCE_NOT_BOOTSTRAPPED")
        return 1
    print("outbound_enabled=true")
    print("is_enabled=true")
    print("schedule_enabled=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
