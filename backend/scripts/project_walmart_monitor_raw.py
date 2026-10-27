"""Replay accepted Walmart monitor RAW into typed Listing projections.

Dry-run is the default and always rolls back. This script reads only the local
database; it never creates a provider client or triggers a synchronization job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.walmart_monitor.projection import WalmartMonitorProjectionService  # noqa: E402

CONFIRM_TOKEN = "CONFIRM_WALMART_MONITOR_RAW_PROJECTION"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project stored Walmart monitor RAW without calling external APIs."
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--confirm-token")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.limit <= 10000:
        print("WALMART_MONITOR_PROJECTION_FAILED code=INVALID_LIMIT")
        return 2
    settings = get_settings()
    if (
        args.commit
        and settings.app_env.value == "production"
        and (not args.allow_production or args.confirm_token != CONFIRM_TOKEN)
    ):
        print("WALMART_MONITOR_PROJECTION_FAILED code=PRODUCTION_CONFIRMATION_REQUIRED")
        return 2

    with get_session_factory()() as session:
        try:
            projected = WalmartMonitorProjectionService(session).replay_unprojected(
                limit=args.limit
            )
            if args.commit:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            print("WALMART_MONITOR_PROJECTION_FAILED code=PROJECTION_FAILED")
            return 2
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"projected_targets={projected}")
    print("external_api=NOT_CALLED")
    print("sync=NOT_TRIGGERED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
