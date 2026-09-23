import inspect

from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner


def test_v4_writes_refunds_into_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._write_refunds)

    assert "build_rows" in source
    assert "AfterSalesReasonClassifier" in source
    assert "delete_excluded_rows" in source
    assert "upsert_rows" in source


def test_v4_does_not_reprice_refunds_to_original_sales_day() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._reprice_refunds)

    assert "return 0" in source
    assert "purchaseTimeLocale" not in source
    assert "dws_walmart_refund_business_amounts" not in source


def test_v4_refreshes_only_requested_daily_sales_day() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "_refund_affected_business_dates" not in source
    assert "sales_fact_exists" not in source
    assert "return super()._refresh_daily_sales_mart()" in source


def test_v4_refund_identity_health_reads_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._resolve_refund_items)

    assert "after_sales_refund_items" in source
    assert "refund_effective_date=:day" in source
    assert "fact_walmart_refund_items" not in source
