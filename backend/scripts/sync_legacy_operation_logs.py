"""Safe history preflight and explicitly authorized source-mirror import."""

from __future__ import annotations
import argparse
import os
from app.db.session import get_session_factory
from app.modules.operation_logs.service import import_history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--acknowledge-db-write", action="store_true")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    if args.commit:
        if (
            not args.acknowledge_db_write
            or os.getenv("OPERATION_LOG_DB_WRITE_AUTHORIZED") != "true"
        ):
            raise SystemExit("REFUSED: explicit write authorization required")
        if (
            os.getenv("APP_ENV") == "production"
            and os.getenv("PRODUCTION_LOG_IMPORT_AUTHORIZED") != "true"
        ):
            raise SystemExit("REFUSED: production write authorization required")
    with get_session_factory()() as session:
        result = import_history(session, commit=args.commit, batch_size=args.batch_size)
    # Safe counters only: do not output any SKU, token or raw log.
    print("MODE", "commit" if args.commit else "dry-run")
    for key, value in result.items():
        print(key, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
