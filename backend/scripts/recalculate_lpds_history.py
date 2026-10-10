"""CLI for bounded, controlled LPDS history recalculation.

No external API client is created. Omitting ``--commit`` performs the selected
recalculation mode inside a transaction and then rolls it back.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.lpds_history_recalc_runner import (  # noqa: E402
    LpdsHistoryRecalcError,
    LpdsHistoryRecalcRunner,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recalculate LPDS history from existing database facts without provider calls."
    )
    parser.add_argument("--source-account-ref", required=True)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--mode",
        choices=("canonical", "lpds-only"),
        default="canonical",
        help="Rebuild all MART inputs or preserve historical non-LPDS inputs.",
    )
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument(
        "--dry-run", action="store_true", help="Explicit rollback mode (default)."
    )
    write_mode.add_argument("--commit", action="store_true", help="Persist after all gates pass.")
    parser.add_argument("--restore-from", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--limit-days", type=int, default=1)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--confirm-token")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    del args.dry_run  # absence of --commit is intentionally the default dry-run gate
    try:
        settings = get_settings()
        result = LpdsHistoryRecalcRunner(
            get_session_factory(),
            app_env=settings.app_env,
        ).run(
            source_account_ref=args.source_account_ref,
            exact_date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
            limit_days=args.limit_days,
            commit=args.commit,
            backup_dir=args.backup_dir,
            allow_production=args.allow_production,
            confirm_token=args.confirm_token,
            restore_from=args.restore_from,
            recalculation_mode=args.mode,
        )
    except LpdsHistoryRecalcError as error:
        print(f"LPDS_HISTORY_FAILED code={error}")
        return 2
    except Exception:
        print("LPDS_HISTORY_FAILED code=LPDS_UNEXPECTED_ERROR")
        return 2

    for line in result.safe_lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
