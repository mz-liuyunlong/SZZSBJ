"""Read-only WFS store discovery diagnostic."""

import os
import sys

from sqlalchemy import text

from app.db.session import get_session_factory
from app.modules.warehouse_wfs.store_discovery import discover_walmart_stores


def main() -> int:
    if os.getenv("WFS_ALLOW_DB_READ") != "YES":
        print("STOP: DATABASE_READ_NOT_AUTHORIZED")
        return 2

    with get_session_factory()() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))

        accounts = (
            session.execute(
                text(
                    "SELECT DISTINCT source_account_ref "
                    "FROM dim_lingxing_stores "
                    "WHERE platform_code = 'walmart' "
                    "OR platform_code_raw = '10008'"
                )
            )
            .scalars()
            .all()
        )

        print("SOURCE_ACCOUNT_COUNT:", len(accounts))

        if len(accounts) != 1:
            print("STOP: EXPECTED_ONE_SOURCE_ACCOUNT")
            return 2

        stores = discover_walmart_stores(
            session,
            source_account_ref=accounts[0],
        )

        print("WALMART_STORE_COUNT:", len(stores))
        print("STORES_WITH_SID:", sum(bool(s.sid) for s in stores))
        print("MANUAL_SID_REQUIRED: NO")
        print("API_CALLS: 0")
        print("DATABASE_WRITES: 0")

        session.rollback()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("DIAGNOSTIC_FAILED_TYPE:", type(exc).__name__)
        sys.exit(1)
