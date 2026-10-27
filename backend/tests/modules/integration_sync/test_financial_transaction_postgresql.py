"""PostgreSQL transaction-boundary regression for capture and financial MART separation.

Runs only against an explicitly provisioned, isolated local WFS CI database.
All evidence is synthetic and placed in temporary tables, never production tables.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_mart_invariants import DataPagesMartInvariantError
from app.modules.integration_sync.data_pages_real_sync import DataPagesRealSyncSummary
from app.modules.integration_sync.execution import SyncRunExecutionService


def _dedicated_test_url():
    if os.environ.get("WFS_AUTO_CASE_POSTGRES_TESTS") != "1":
        pytest.skip("requires isolated WFS PostgreSQL integration-test service")
    if os.environ.get("APP_ENV") != "test":
        pytest.fail("financial transaction test refuses non-test environment")
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("TEST_DATABASE_URL is required")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.port != 5432
        or url.username != "wfs_auto_case_ci"
        or url.database != "wfs_auto_case_ci"
        or not url.password
        or url.query
    ):
        pytest.fail("refusing PostgreSQL target outside isolated WFS CI database")
    return url


def test_refund_source_commit_survives_financial_rollback() -> None:
    engine = create_engine(_dedicated_test_url(), hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("select current_database(), current_user")).one() == (
                "wfs_auto_case_ci",
                "wfs_auto_case_ci",
            )
            # TEMP tables are session-local and cannot alter real financial tables.
            connection.execute(
                text("create temporary table sync_source_capture (qty int not null)")
            )
            connection.execute(
                text("create temporary table sync_validated_daily (amount numeric not null)")
            )
            connection.execute(
                text("create temporary table sync_validated_profit (amount numeric not null)")
            )
            connection.execute(text("insert into sync_validated_daily values (25.98)"))
            connection.execute(text("insert into sync_validated_profit values (6.12)"))
            connection.commit()

            with Session(bind=connection) as session:
                service = SyncRunExecutionService(session)
                runner = MagicMock()
                runner.business_date = date(2026, 10, 25)
                runner.heartbeat = None
                runner.page_size = 100
                runner._fetch_offset_all.return_value = [{"store_id": "synthetic-store"}]
                runner._fetch_return_all.return_value = [{"return": "synthetic-refund"}]
                runner._write_stores.return_value = 1
                runner._resolve_refund_items.return_value = 0
                runner._refund_affected_business_dates = ()
                runner.summary = DataPagesRealSyncSummary(
                    source_account_ref="synthetic-account",
                    business_date=runner.business_date,
                )

                def persist_source(_refunds):
                    session.execute(text("insert into sync_source_capture values (2)"))
                    return 1

                def fail_financial_validation():
                    session.execute(text("update sync_validated_daily set amount = 0"))
                    session.execute(text("update sync_validated_profit set amount = 0"))
                    raise DataPagesMartInvariantError(
                        "DATA_PAGES_SEM_SPEND_UNATTRIBUTED",
                        business_date=runner.business_date,
                    )

                runner._write_refunds.side_effect = persist_source
                runner._refresh_daily_sales_mart.side_effect = fail_financial_validation

                with pytest.raises(
                    DataPagesMartInvariantError,
                    match="DATA_PAGES_SEM_SPEND_UNATTRIBUTED",
                ):
                    service._execute_data_pages_interface("walmartReturnOrderList", runner)
                assert runner._source_fact_commit_completed is True
                # Match the rollback path in _execute_data_pages_run.
                session.rollback()
                assert session.scalar(text("select sum(qty) from sync_source_capture")) == 2
                assert session.scalar(text("select amount from sync_validated_daily")) == 25.98
                assert session.scalar(text("select amount from sync_validated_profit")) == 6.12
                runner._refresh_order_profit_mart.assert_not_called()
    finally:
        engine.dispose()
