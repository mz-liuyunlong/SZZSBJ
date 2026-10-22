"""Explicitly authorized, database-free Huizhou collection. No credentials in arguments."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from time import sleep
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.integrations.lingxing.client import LingxingReadonlyClient
from app.integrations.lingxing.file_settings import LingxingFileSettings
from app.integrations.lingxing.pmc_domestic_contracts import (
    pmc_domestic_response_succeeded,
)
from app.integrations.lingxing.token_manager import (
    LingxingTokenClient,
    LingxingTokenManager,
)
from app.modules.pmc_domestic.inbound_collector import export_inbound_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-account", required=True)
    parser.add_argument("--warehouse-id", required=True, help="Verified Huizhou warehouse ID")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--end", type=date.fromisoformat, required=True, help="Exclusive business date"
    )
    parser.add_argument("--source-timezone", help="Only set after confirming provider timezone")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()
    if os.getenv("PMC_DOMESTIC_CSV_EXPORT_AUTHORIZED", "").lower() != "true":
        print("INBOUND_CSV_EXPORT_NOT_AUTHORIZED")
        return 2
    client = token_client = None
    try:
        settings = LingxingFileSettings()
        if not settings.lingxing_enable_real_calls or not settings.lingxing_enable_token_requests:
            raise ValueError("disabled")
        if args.source_timezone:
            ZoneInfo(args.source_timezone)
        # These existing clients consume only Lingxing settings in this path. The
        # structural adapter deliberately supplies no database/app environment.
        runtime = cast(Settings, settings)
        token_client = LingxingTokenClient(runtime)
        manager = LingxingTokenManager(token_client, runtime)
        client = LingxingReadonlyClient(
            runtime, token_provider=manager, success_evaluator=pmc_domestic_response_succeeded
        )
        run_id = str(uuid4())

        def fetch(path, body):
            sleep(1.25)
            return client.fetch_inbound_page(
                api_path=path,
                body=body,
                source_account_ref=args.source_account,
                run_id=run_id,
                work_item_id=str(uuid4()),
            )

        result = export_inbound_csv(
            fetch,
            output=args.output,
            account=args.source_account,
            warehouse=args.warehouse_id,
            start=args.start,
            end=args.end,
            max_pages=args.max_pages,
            source_timezone=args.source_timezone,
        )
        print(
            "INBOUND_CSV_EXPORT_COMPLETE",
            "rows=" + str(result["files"]["inbound_board_preview.csv"]["rows"]),
        )
        return 0
    except Exception:
        print("INBOUND_CSV_EXPORT_FAILED: check safe manifest or required configuration")
        return 1
    finally:
        if client:
            client.close()
        if token_client:
            token_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
