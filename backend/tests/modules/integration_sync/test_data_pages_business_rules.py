from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_business_rules import (
    CHINA_TZ,
    DataPagesRealSyncRunner,
    _is_valid_sample,
    _refund_amounts,
    _sample_window_china,
)


class _ScalarResult:
    def scalar_one(self) -> int:
        return 0


class _MappingResult:
    def __init__(self) -> None:
        self._row = None

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> None:
        return self._row


class _CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def execute(self, statement: object, params: dict[str, Any] | None = None) -> _ScalarResult:
        self.calls.append((str(statement), params))
        return _ScalarResult()


class _MatchCaptureSession(_CaptureSession):
    def execute(self, statement: object, params: dict[str, Any] | None = None) -> _MappingResult:
        self.calls.append((str(statement), params))
        return _MappingResult()


def _runner(session: object | None = None) -> DataPagesRealSyncRunner:
    runner = DataPagesRealSyncRunner(
        session=cast(Session, session or object()),
        client=None,
        source_account_ref="primary",
        business_date=date(2026, 9, 1),
        page_size=100,
        campaign_type="SP",
        max_advertisers=10,
    )
    runner.store_ids = ("store-a",)
    return runner


def test_sample_order_window_converts_fixed_utc_minus_7_to_china_time() -> None:
    start_at, end_at = _sample_window_china(date(2026, 9, 1))

    assert start_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-01 15:00:00"
    assert end_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-02 14:59:59"
    assert start_at.utcoffset() == timedelta(hours=8)
    assert end_at.utcoffset() == timedelta(hours=8)


def test_sample_order_request_uses_special_window_without_changing_generic_order_body() -> None:
    runner = _runner()

    sample_body = runner._sample_order_body(offset=0, size=100)
    generic_body = runner._order_body(offset=0, size=100)

    assert (
        datetime.fromtimestamp(sample_body["start_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-01 15:00:00"
    )
    assert (
        datetime.fromtimestamp(sample_body["end_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-02 14:59:59"
    )
    assert (
        datetime.fromtimestamp(generic_body["start_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-01 00:00:00"
    )
    assert (
        datetime.fromtimestamp(generic_body["end_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-01 23:59:59"
    )


def test_sample_rule_requires_zero_total_and_no_cancel_time() -> None:
    assert _is_valid_sample(Decimal("0"), None) is True
    assert _is_valid_sample(Decimal("0.0000"), "") is True
    assert _is_valid_sample(Decimal("0"), "2026-09-01 10:00:00") is False
    assert _is_valid_sample(Decimal("1"), None) is False


def test_sample_writer_keeps_required_business_fields() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    written = runner._write_sample_orders(
        [
            {
                "global_order_no": "global-1",
                "store_id": "store-a",
                "store_name": "Store A",
                "amount_currency": "USD",
                "transaction_info": [{"order_total_amount": "0"}],
                "platform_info": [{"platform_code": "10008", "cancel_time": ""}],
                "item_info": [
                    {
                        "id": "line-1",
                        "platform_order_no": "platform-1",
                        "local_sku": "SKU-1",
                        "msku": "MSKU-1",
                        "quantity": "2",
                        "unit_price_amount": "9.99",
                    }
                ],
            }
        ]
    )

    assert written == 1
    params = session.calls[0][1]
    assert params is not None
    assert params["platform_order_no"] == "platform-1"
    assert params["source_order_line_id"] == "line-1"
    assert params["store_name"] == "Store A"
    assert params["local_sku"] == "SKU-1"
    assert params["msku"] == "MSKU-1"
    assert params["quantity"] == Decimal("2")
    assert params["unit_price_amount"] == Decimal("9.99")
    assert params["order_total_amount"] == Decimal("0")
    assert params["platform_code"] == "10008"
    assert params["is_valid_sample"] is True


def test_refund_quantity_comes_from_return_api_quantity_display() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    written = runner._write_refunds(
        [
            {
                "returnType": "REFUND",
                "returnOrderId": "return-1",
                "storeId": "store-a",
                "customerOrderId": "order-1",
                "items": [
                    {
                        "returnLineId": "return-line-1",
                        "purchaseOrderId": "purchase-1",
                        "itemId": "item-1",
                        "msku": "MSKU-1",
                        "localSku": "SKU-1",
                        "quantityDisplay": "3.5",
                        "lineTotalAmount": "59.50",
                        "lineTotalCurrency": "USD",
                    }
                ],
            }
        ]
    )

    assert written == 1
    params = session.calls[0][1]
    assert params is not None
    assert params["quantity"] == Decimal("3.5")

    gross, commission, net = _refund_amounts(
        Decimal("20"),
        params["quantity"],
        Decimal("0.15"),
    )
    assert gross == Decimal("70.0")
    assert commission == Decimal("10.500")
    assert net == Decimal("59.500")


def test_refund_order_match_types_nullable_text_parameters() -> None:
    session = _MatchCaptureSession()
    runner = _runner(session)

    matched = runner._match_refund_order_line(
        {
            "customer_order_id": "order-1",
            "purchase_order_id": None,
            "store_id": None,
            "item_id": None,
            "local_sku": "SKU-1",
            "msku": None,
        }
    )

    assert matched is None
    sql = session.calls[0][0]
    assert "cast(:customer_order_id as text) is not null" in sql
    assert "cast(:purchase_order_id as text) is not null" in sql
    assert "cast(:store_id as text) is null" in sql
    assert "cast(:item_id as text) is not null" in sql
    assert "trim(cast(:local_sku as text))" in sql
    assert "cast(:msku as text) is not null" in sql


def test_daily_sales_mart_is_based_on_salestat_and_joins_sku_cost_sources() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    runner._refresh_daily_sales_mart()

    insert_sql = session.calls[1][0]
    assert "from fact_walmart_sales_item_daily" in insert_sql
    assert "fact_walmart_sample_order_items" in insert_sql
    assert "dws_walmart_refund_business_amounts" in insert_sql
    assert "dwd_lingxing_sku_product_info_current" in insert_sql
    assert "dws_product_management_pricing_current" in insert_sql
    assert "ref_store_commission_rule_versions" in insert_sql
    assert "'basis','fact_walmart_sales_item_daily'" in insert_sql
