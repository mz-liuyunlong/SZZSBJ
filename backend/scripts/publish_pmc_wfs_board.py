"""Publish a WFS shipment-board version from succeeded ODS runs; no source traffic."""

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.models import IntegrationSyncRun  # noqa: E402
from app.modules.pmc_wfs.board_publisher import WfsBoardPublisher  # noqa: E402


def _latest_run(session, account: str, interface_key: str) -> UUID | None:
    return session.scalar(
        select(IntegrationSyncRun.id)
        .where(
            IntegrationSyncRun.provider == "lingxing",
            IntegrationSyncRun.interface_key == interface_key,
            IntegrationSyncRun.source_account_ref == account,
            IntegrationSyncRun.status == "succeeded",
        )
        .order_by(IntegrationSyncRun.finished_at.desc())
        .limit(1)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-account", required=True)
    parser.add_argument("--cargo-run-id", type=UUID)
    parser.add_argument("--shipping-run-id", type=UUID)
    parser.add_argument(
        "--latest", action="store_true", help="use the latest succeeded run of each feed"
    )
    args = parser.parse_args()
    if os.getenv("PMC_WFS_BOARD_PUBLISH_AUTHORIZED", "").lower() != "true":
        print("WFS_BOARD_PUBLISH_NOT_AUTHORIZED")
        return 2
    try:
        register_productlist_sync_models()
        with get_session_factory()() as session:
            cargo_run_id = args.cargo_run_id
            shipping_run_id = args.shipping_run_id
            if args.latest:
                cargo_run_id = cargo_run_id or _latest_run(
                    session, args.source_account, "wfsCargoPage"
                )
                shipping_run_id = shipping_run_id or _latest_run(
                    session, args.source_account, "wfsShippingListPage"
                )
            if cargo_run_id is None:
                print("WFS_BOARD_CARGO_RUN_REQUIRED")
                return 2
            result = WfsBoardPublisher(session).publish(
                account=args.source_account,
                cargo_run_id=cargo_run_id,
                shipping_run_id=shipping_run_id,
            )
        print("WFS_BOARD_PUBLISHED", result.publication_id)
        print(f"board_rows={result.rows}")
        print(f"cargos_without_shipping={result.cargos_without_shipping}")
        print(f"coverage={result.coverage_start.isoformat()}..{result.coverage_end.isoformat()}")
        print(f"source_observed_at={result.source_observed_at.isoformat()}")
        return 0
    except Exception as error:
        code = getattr(error, "code", None) or type(error).__name__
        print(f"WFS_BOARD_PUBLICATION_FAILED {code}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
