from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from sqlalchemy import text

from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session_factory
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.data_pages_business_rules_v2 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_real_sync import (
    AUTHORIZED_ENV,
    DataPagesRealSyncError,
    data_pages_client,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Order V2 sample candidates, Return/Refund business amounts, "
            "and SaleStat-based MART rows without touching Ads or SaleStat facts."
        )
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--source-account-ref", required=True)
    parser.add_argument("--page-size", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if os.environ.get(AUTHORIZED_ENV) != "true":
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_NOT_AUTHORIZED")
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REQUIRES_PRODUCTION_ENV")
    if not settings.lingxing_enable_real_calls:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REAL_CALLS_DISABLED")
    if not 1 <= args.page_size <= 200:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_PAGE_SIZE_INVALID")

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise DataPagesRealSyncError("DATA_PAGES_BACKFILL_DATE_RANGE_INVALID")
    account = args.source_account_ref.strip()
    if not account or account != args.source_account_ref:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_SCOPE_INVALID")

    session_factory = get_session_factory()
    with session_factory() as bootstrap_session:
        IntegrationCatalogService(bootstrap_session).bootstrap_data_pages_governance(account)

    with data_pages_client() as client:
        day = start_date
        while day <= end_date:
            with session_factory() as session:
                runner = DataPagesRealSyncRunner(
                    session=session,
                    client=client,
                    source_account_ref=account,
                    business_date=day,
                    page_size=args.page_size,
                    campaign_type="SP",
                    max_advertisers=1,
                )
                runner.store_ids = tuple(
                    str(row[0])
                    for row in session.execute(
                        text(
                            "select store_id from dim_lingxing_stores "
                            "where source_account_ref=:account and platform_code_raw='10008' "
                            "order by store_id"
                        ),
                        {"account": account},
                    ).all()
                    if row[0]
                )
                if not runner.store_ids:
                    raise DataPagesRealSyncError("DATA_PAGES_NO_WALMART_STORES")

                try:
                    orders = runner._fetch_offset_all(
                        "order_v2_list",
                        runner._order_body,
                        minimum_page_size=20,
                    )
                    sample_candidates = runner._fetch_offset_all(
                        "order_v2_list",
                        runner._sample_order_body,
                        minimum_page_size=20,
                    )
                    refunds = runner._fetch_return_all()

                    order_rows = runner._write_orders(orders)
                    sample_rows = runner._write_sample_orders(sample_candidates)
                    refund_rows = runner._write_refunds(refunds)
                    unresolved_orders = runner._resolve_order_items()
                    unresolved_samples = runner._resolve_sample_items()
                    unresolved_refunds = runner._resolve_refund_items()
                    unpriced_refunds = runner._reprice_refunds()
                    daily_rows = runner._refresh_daily_sales_mart()
                    profit_rows = runner._refresh_order_profit_mart()
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

                print(
                    f"{day} orders={order_rows} samples={sample_rows} refunds={refund_rows} "
                    f"order_unresolved={unresolved_orders} sample_unresolved={unresolved_samples} "
                    f"refund_unresolved={unresolved_refunds} refund_unpriced={unpriced_refunds} "
                    f"daily_mart={daily_rows} order_profit_mart={profit_rows}"
                )
            day += timedelta(days=1)

    print("DATA_PAGES_BUSINESS_RULE_BACKFILL_COMPLETE")
    print("salestat=NOT_TOUCHED")
    print("ads=NOT_TOUCHED")
    print("mysql=NOT_TOUCHED")


if __name__ == "__main__":
    main()
