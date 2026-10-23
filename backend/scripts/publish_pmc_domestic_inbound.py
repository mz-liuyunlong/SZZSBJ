"""Explicit DB publication from successful ODS runs; no source traffic."""

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_session_factory
from app.modules.pmc_domestic.inbound_publisher import InboundPublisher


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-account", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--batch-run-id", type=UUID, required=True)
    parser.add_argument("--statement-run-id", type=UUID, action="append", required=True)
    parser.add_argument("--source-timezone")
    args = parser.parse_args()
    if os.getenv("PMC_DOMESTIC_INBOUND_DB_PUBLISH_AUTHORIZED", "").lower() != "true":
        print("INBOUND_DB_PUBLISH_NOT_AUTHORIZED")
        return 2
    try:
        register_productlist_sync_models()
        with get_session_factory()() as session:
            identity = InboundPublisher(session).publish(
                account=args.source_account,
                warehouse=args.warehouse_id,
                batch_run_id=args.batch_run_id,
                statement_run_ids=args.statement_run_id,
                source_timezone=args.source_timezone,
            )
        print("INBOUND_PUBLISHED", identity)
        return 0
    except Exception:
        print("INBOUND_PUBLICATION_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
