from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session_factory
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_real_sync import (
    AUTHORIZED_ENV,
    DataPagesRealSyncError,
    data_pages_client,
)

FULL_HISTORY_AUTHORIZED_ENV = "DATA_PAGES_FULL_HISTORY_BACKFILL_AUTHORIZED"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full governed DATA-PAGES sync for a historical date range, including "
            "SaleStat, orders/samples, refunds, ads and MART refreshes, then optionally "
            "refresh one final acceptance date."
        )
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--extra-date", action="append", default=[])
    parser.add_argument("--final-refresh-date")
    parser.add_argument("--source-account-ref", required=True)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--campaign-type", default="SP")
    parser.add_argument("--max-advertisers", type=int, default=20)
    return parser.parse_args()


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def main() -> None:
    args = parse_args()
    if os.environ.get(AUTHORIZED_ENV) != "true":
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_NOT_AUTHORIZED")
    if os.environ.get(FULL_HISTORY_AUTHORIZED_ENV) != "true":
        raise DataPagesRealSyncError("DATA_PAGES_FULL_HISTORY_BACKFILL_NOT_AUTHORIZED")

    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REQUIRES_PRODUCTION_ENV")
    if not settings.lingxing_enable_real_calls:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REAL_CALLS_DISABLED")
    if not 1 <= args.page_size <= 200:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_PAGE_SIZE_INVALID")
    if args.max_advertisers < 1:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_ADVERTISER_LIMIT_INVALID")

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise DataPagesRealSyncError("DATA_PAGES_FULL_HISTORY_DATE_RANGE_INVALID")

    account = args.source_account_ref.strip()
    if not account or account != args.source_account_ref:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_SCOPE_INVALID")

    days = set(_date_range(start_date, end_date))
    for raw_day in args.extra_date:
        days.add(date.fromisoformat(raw_day))
    ordered_days = sorted(days)
    final_refresh_date = (
        date.fromisoformat(args.final_refresh_date) if args.final_refresh_date else None
    )

    session_factory = get_session_factory()
    with session_factory() as bootstrap_session:
        IntegrationCatalogService(bootstrap_session).bootstrap_data_pages_governance(account)

    with data_pages_client() as client:
        for business_date in ordered_days:
            with session_factory() as session:
                summary = DataPagesRealSyncRunner(
                    session=session,
                    client=client,
                    source_account_ref=account,
                    business_date=business_date,
                    page_size=args.page_size,
                    campaign_type=args.campaign_type,
                    max_advertisers=args.max_advertisers,
                ).execute()
            print(f"FULL_HISTORY_DAY_COMPLETE business_date={business_date.isoformat()}")
            for line in summary.safe_lines():
                print(line)

        if final_refresh_date is not None:
            with session_factory() as session:
                summary = DataPagesRealSyncRunner(
                    session=session,
                    client=client,
                    source_account_ref=account,
                    business_date=final_refresh_date,
                    page_size=args.page_size,
                    campaign_type=args.campaign_type,
                    max_advertisers=args.max_advertisers,
                ).execute()
            print(
                "FULL_HISTORY_FINAL_REFRESH_COMPLETE "
                f"business_date={final_refresh_date.isoformat()}"
            )
            for line in summary.safe_lines():
                print(line)

    print("DATA_PAGES_FULL_HISTORY_BACKFILL_COMPLETE")
    print("postgresql=WRITTEN")
    print("external_api=CALLED")
    print("mysql=NOT_TOUCHED")


if __name__ == "__main__":
    main()
