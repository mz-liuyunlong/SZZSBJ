import inspect

from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner


def test_v4_writes_refunds_into_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._write_refunds)

    assert "build_rows" in source
    assert "AfterSalesReasonClassifier" in source
    assert "delete_excluded_rows" in source
    assert "upsert_rows" in source


def test_v4_collects_refund_purchase_days_only_when_salestat_exists() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._reprice_refunds)

    assert "r.return_order_at::date=:refund_day" in source
    assert "r.purchase_time_at::date" in source
    assert "fact_walmart_sales_item_daily" in source
    assert "s.business_date_la=r.purchase_time_at::date" in source
    assert "s.allocation_status='direct'" in source
    assert "interval '15 hours'" not in source
    assert "dws_walmart_refund_business_amounts" not in source


def test_v4_refreshes_affected_refund_purchase_days() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "_refund_affected_business_dates" in source
    assert "self._refresh_order_profit_mart()" in source
    assert "return super()._refresh_daily_sales_mart()" in source


def test_v4_refund_identity_health_reads_refund_management_fact() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._resolve_refund_items)

    assert "after_sales_refund_items" in source
    assert "refund_effective_date=:day" in source
    assert "fact_walmart_refund_items" not in source
